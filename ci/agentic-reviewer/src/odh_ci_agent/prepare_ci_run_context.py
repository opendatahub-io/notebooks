#!/usr/bin/env python3
"""Prepare bounded CI context for the Antigravity matrix-build summarizer."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from odh_ci_agent.ci_summary import (
    build_clusters,
    int_value,
    logs_fully_grounded,
    marker_for_run,
    render_progress_comment,
    utc_now_iso,
)
from odh_ci_agent.github_api import gh_api_json, gh_api_list_pages, gh_api_pages, gh_job_log
from odh_ci_agent.patch_excerpt import capped_patch_excerpt
from odh_ci_agent.source_workspace import resolve_source_workspace

MAX_LOG_LINES = 150
MAX_LOG_CHARS = 12_000
MAX_FAILED_JOBS_WITH_LOGS = 15
FAILED_STEP_CONTEXT_BEFORE = 10
FAILED_STEP_CONTEXT_AFTER = 40
FAILED_STEP_ERROR_TAIL_BEFORE = 10
FAILED_STEP_ERROR_TAIL_AFTER = 5
WHOLE_LOG_CONTEXT_BEFORE = 2
WHOLE_LOG_CONTEXT_AFTER = 5
MAX_WHOLE_LOG_CONTEXTS = 4
MAX_CHANGED_FILES_WITH_PATCH = 20
MAX_PATCH_LINES = 40

GITHUB_ERROR_RE = re.compile(r"##\[error\]")
LOG_TIMESTAMP_RE = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s?(?P<message>.*)$")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def output_path(env_name: str, default_name: str) -> str:
    return os.environ.get(env_name, default_name)


def failed_step_name(job: Mapping[str, object]) -> str:
    step = selected_step(job)
    if step is None:
        return "Unknown step"
    return str(step.get("name", "Unknown step"))


def selected_step(job: Mapping[str, object]) -> Mapping[str, object] | None:
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        return None

    failed_steps = [
        step for step in steps if isinstance(step, Mapping) and step.get("conclusion") in {"failure", "cancelled"}
    ]
    if failed_steps:
        return failed_steps[-1]

    in_progress_steps = [step for step in steps if isinstance(step, Mapping) and step.get("status") == "in_progress"]
    if in_progress_steps:
        return in_progress_steps[-1]

    return None


def run_mode(run_status: str, run_conclusion: str | None, failed_count: int) -> str:
    if run_status == "completed":
        return "final"
    if failed_count > 0 or run_conclusion in {"failure", "cancelled"}:
        return "failure"
    return "progress"


def progress_counts(jobs: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = {
        "total": len(jobs),
        "completed": 0,
        "passed": 0,
        "failed": 0,
        "cancelled": 0,
        "skipped": 0,
        "in_progress": 0,
        "queued": 0,
    }
    for job in jobs:
        status = str(job.get("status", ""))
        conclusion = job.get("conclusion")
        if status == "completed":
            counts["completed"] += 1
            if conclusion == "success":
                counts["passed"] += 1
            elif conclusion == "failure":
                counts["failed"] += 1
            elif conclusion == "cancelled":
                counts["cancelled"] += 1
            elif conclusion == "skipped":
                counts["skipped"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
        else:
            counts["queued"] += 1
    return counts


def is_matrix_job_name(job_name: str) -> bool:
    return "·" in job_name or "${{ matrix.target }}" in job_name


def matrix_job_counts(jobs: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "cancelled": 0,
        "skipped": 0,
    }
    for job in jobs:
        job_name = str(job.get("name", ""))
        if not is_matrix_job_name(job_name):
            continue
        counts["total"] += 1
        conclusion = job.get("conclusion")
        if conclusion == "success":
            counts["passed"] += 1
        elif conclusion == "failure":
            counts["failed"] += 1
        elif conclusion == "cancelled":
            counts["cancelled"] += 1
        elif conclusion == "skipped":
            counts["skipped"] += 1
    return counts


def parse_iso8601_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def strip_gh_log_prefix(line: str) -> str:
    parts = line.split("\t", maxsplit=2)
    candidate = parts[2] if len(parts) == 3 else line
    match = LOG_TIMESTAMP_RE.match(candidate)
    if match:
        candidate = match.group("message")
    return ANSI_ESCAPE_RE.sub("", candidate)


def log_line_timestamp(line: str) -> datetime | None:
    parts = line.split("\t", maxsplit=2)
    candidate = parts[2] if len(parts) == 3 else line
    match = LOG_TIMESTAMP_RE.match(candidate)
    if not match:
        return None
    return parse_iso8601_timestamp(match.group("timestamp"))


def is_error_anchor(line: str) -> bool:
    if GITHUB_ERROR_RE.search(line) is not None:
        return True

    stripped = line.strip()
    lowered = stripped.lower()
    return (
        stripped.startswith(
            ("Error:", "ERROR ", "Exception:", "Traceback (most recent call last):", "FAILED ", "SUBFAILED")
        )
        or "permission denied" in lowered
        or "fetcherror" in lowered
        or "no module named" in lowered
        or "=> not found" in lowered
        or "unsatisfied dependencies" in lowered
        or "make: ***" in lowered
        or "assert " in lowered
    )


def error_anchor_kind(line: str) -> str | None:
    if GITHUB_ERROR_RE.search(line) is not None:
        return "github_error"

    stripped = line.strip()
    lowered = stripped.lower()
    if "permission denied" in lowered:
        return "permission_denied"
    if "fetcherror" in lowered or stripped.startswith(("Error:", "ERROR ")):
        return "error"
    if stripped.startswith(("Exception:", "Traceback (most recent call last):")):
        return "exception"
    if stripped.startswith(("FAILED ", "SUBFAILED")):
        return "failed_test"
    if "=> not found" in lowered or "unsatisfied dependencies" in lowered:
        return "linker"
    if "no module named" in lowered:
        return "missing_module"
    if "make: ***" in lowered:
        return "make"
    if "assert " in lowered:
        return "assertion"
    return None


def is_noise_line(line: str) -> bool:
    stripped = line.strip()
    lowered = stripped.lower()
    return (
        "kernel:" in lowered
        or "journalctl --no-pager -k" in lowered
        or "run sudo dmesg" in lowered
        or stripped.startswith("Post job cleanup.")
    )


def clip_excerpt(lines: Sequence[str]) -> str:
    excerpt = "\n".join(lines)
    if len(excerpt) <= MAX_LOG_CHARS:
        return excerpt

    head_keep = max(1, len(lines) // 3)
    tail_keep = max(1, len(lines) // 3)
    clipped = [*list(lines[:head_keep]), "...", *list(lines[-tail_keep:])]
    excerpt = "\n".join(clipped)
    if len(excerpt) <= MAX_LOG_CHARS:
        return excerpt
    return excerpt[-MAX_LOG_CHARS:]


def merge_context_windows(anchors: Sequence[int], *, before: int, after: int, line_count: int) -> list[tuple[int, int]]:
    if not anchors:
        return []

    windows: list[tuple[int, int]] = []
    for anchor in anchors:
        start = max(0, anchor - before)
        end = min(line_count, anchor + after + 1)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
    return windows


def whole_log_error_contexts(log_text: str) -> list[str]:
    normalized_lines = [
        line
        for line in (strip_gh_log_prefix(raw_line) for raw_line in log_text.splitlines())
        if line and not is_noise_line(line)
    ]
    if not normalized_lines:
        return []

    anchor_indices: list[int] = []
    previous_anchor_kind: str | None = None
    for index, line in enumerate(normalized_lines):
        kind = error_anchor_kind(line)
        if kind is None:
            previous_anchor_kind = None
            continue

        if kind == "github_error":
            anchor_indices.append(index)
            previous_anchor_kind = kind
            continue

        if kind == previous_anchor_kind:
            continue

        anchor_indices.append(index)
        previous_anchor_kind = kind

    windows = merge_context_windows(
        anchor_indices,
        before=WHOLE_LOG_CONTEXT_BEFORE,
        after=WHOLE_LOG_CONTEXT_AFTER,
        line_count=len(normalized_lines),
    )
    rendered: list[str] = []
    for start, end in windows[:MAX_WHOLE_LOG_CONTEXTS]:
        window_lines = list(normalized_lines[start:end])
        next_step_indices = [
            index for index, line in enumerate(window_lines[1:], start=1) if line.startswith("##[group]Run ")
        ]
        if next_step_indices:
            window_lines = window_lines[: next_step_indices[0]]
        rendered.append(clip_excerpt(window_lines))
    return rendered


def failed_step_excerpt(log_text: str, job: Mapping[str, object]) -> str:
    step = selected_step(job)
    if step is None:
        return ""

    raw_lines = log_text.splitlines()
    if not raw_lines:
        return ""

    step_start = parse_iso8601_timestamp(step.get("started_at"))
    step_end = parse_iso8601_timestamp(step.get("completed_at"))
    if step_start is None:
        return ""
    if step_end is None:
        step_end = step_start + timedelta(minutes=10)
    else:
        # Include the GitHub "process completed with exit code" footer line emitted
        # immediately after the step's last timestamped output.
        step_end += timedelta(seconds=2)

    matching_indices = [
        index
        for index, raw_line in enumerate(raw_lines)
        if (timestamp := log_line_timestamp(raw_line)) is not None and step_start <= timestamp <= step_end
    ]
    if not matching_indices:
        return ""

    normalized = [strip_gh_log_prefix(raw_line) for raw_line in raw_lines]
    step_lines = normalized[matching_indices[0] : matching_indices[-1] + 1]
    if not step_lines:
        return ""

    github_error_indices = [index for index, line in enumerate(step_lines) if GITHUB_ERROR_RE.search(line)]
    if github_error_indices:
        step_lines = step_lines[: github_error_indices[0] + 1]

    anchor_indices = [index for index, line in enumerate(step_lines) if is_error_anchor(line)]
    if not anchor_indices:
        return clip_excerpt(step_lines[-MAX_LOG_LINES:])

    first_anchor = anchor_indices[0]
    last_anchor = anchor_indices[-1]
    excerpt_lines = step_lines[
        max(0, first_anchor - FAILED_STEP_CONTEXT_BEFORE) : min(
            len(step_lines),
            first_anchor + FAILED_STEP_CONTEXT_AFTER,
        )
    ]

    if last_anchor > first_anchor + FAILED_STEP_CONTEXT_AFTER:
        tail_start = max(0, last_anchor - FAILED_STEP_ERROR_TAIL_BEFORE)
        tail_end = min(len(step_lines), last_anchor + FAILED_STEP_ERROR_TAIL_AFTER)
        excerpt_lines = [*excerpt_lines, "...", *step_lines[tail_start:tail_end]]

    return clip_excerpt(excerpt_lines)


def fetch_job_log(repository: str, job_id: int) -> tuple[str, str]:
    try:
        log_text = gh_job_log(repository, job_id, timeout=180)
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"

    return log_text, ""


def build_failed_jobs(
    repository: str,
    run_id: int,
    jobs: Sequence[Mapping[str, object]],
    *,
    include_logs: bool,
) -> list[dict[str, object]]:
    failed_jobs: list[dict[str, object]] = []
    for index, job in enumerate(jobs):
        if job.get("conclusion") not in {"failure", "cancelled"}:
            continue

        log_tail = ""
        log_excerpt = ""
        error_contexts: list[str] = []
        log_error = ""
        if include_logs and len(failed_jobs) < MAX_FAILED_JOBS_WITH_LOGS:
            job_log, log_error = fetch_job_log(repository, int_value(job["id"]))
            if not log_error:
                log_excerpt = failed_step_excerpt(job_log, job)
                log_tail = log_excerpt
                error_contexts = whole_log_error_contexts(job_log)

        failed_jobs.append(
            {
                "id": int_value(job["id"]),
                "name": str(job.get("name", "")),
                "failed_step": failed_step_name(job),
                "conclusion": str(job.get("conclusion", "")),
                "error_contexts": error_contexts,
                "index": index,
                "log_error": log_error or None,
                "log_excerpt": log_excerpt,
                "log_tail": log_tail,
                "status": str(job.get("status", "")),
                "url": str(job.get("html_url", "")),
            }
        )

    return failed_jobs


def write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(content)


def write_github_output(key: str, value: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as file_handle:
        print(f"{key}={value}", file=file_handle)


def pull_request_context(repository: str, pr_number: int) -> dict[str, object]:
    pr = gh_api_json(f"repos/{repository}/pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise SystemExit("Expected pull request response to be a JSON object")

    files = gh_api_list_pages(f"repos/{repository}/pulls/{pr_number}/files", timeout=180)
    typed_files = [file_info for file_info in files if isinstance(file_info, dict)]

    changed_files = [
        {
            "additions": file_info.get("additions"),
            "deletions": file_info.get("deletions"),
            "filename": file_info.get("filename"),
            "patch_excerpt": capped_patch_excerpt(
                file_info.get("patch") if isinstance(file_info.get("patch"), str) else None,
                max_lines=MAX_PATCH_LINES,
            ),
            "status": file_info.get("status"),
        }
        for file_info in typed_files[:MAX_CHANGED_FILES_WITH_PATCH]
    ]

    return {
        "base_ref": pr["base"]["ref"],
        "body": pr.get("body") or "",
        "changed_files": changed_files,
        "changed_files_omitted": max(0, len(typed_files) - len(changed_files)),
        "head_ref": pr["head"]["ref"],
        "head_sha": pr["head"]["sha"],
        "number": pr_number,
        "title": pr["title"],
    }


def build_context(
    repository: str,
    run: Mapping[str, object],
    jobs: Sequence[Mapping[str, object]],
    pr_context: Mapping[str, object],
    pull_request_number: int | None,
    source_head_sha: str,
    *,
    trigger_job_id: int | None,
    include_logs: bool,
) -> dict[str, object]:
    progress = progress_counts(jobs)
    matrix_progress = matrix_job_counts(jobs)
    run_status = str(run.get("status", ""))
    raw_conclusion = run.get("conclusion")
    run_conclusion = str(raw_conclusion) if raw_conclusion else None
    mode = run_mode(run_status, run_conclusion, progress["failed"])
    run_id = int_value(run["id"])
    failed_jobs = build_failed_jobs(repository, run_id, jobs, include_logs=include_logs)
    in_progress_jobs = [str(job.get("name", "")) for job in jobs if job.get("status") != "completed"]

    trigger_job_name = "workflow update"
    if trigger_job_id is not None:
        for job in jobs:
            if int_value(job["id"]) == trigger_job_id:
                trigger_job_name = str(job.get("name", trigger_job_name))
                break

    updated_at = utc_now_iso()
    context: dict[str, object] = {
        "comment_marker": marker_for_run(run_id, failed_jobs=progress["failed"], updated_at=updated_at),
        "clusters": build_clusters(failed_jobs),
        "failed_jobs": failed_jobs,
        "github_repository": repository,
        "in_progress_jobs": in_progress_jobs,
        "logs_fully_grounded": logs_fully_grounded(failed_jobs),
        "mode": mode,
        "matrix_progress": matrix_progress,
        "pr_number": pull_request_number,
        "progress": progress,
        "pull_request": dict(pr_context),
        "run_conclusion": run_conclusion,
        "run_status": run_status,
        "source_head_sha": source_head_sha,
        "source_workspace": str(resolve_source_workspace()),
        "trigger_job_id": trigger_job_id,
        "trigger_job_name": trigger_job_name,
        "updated_at": updated_at,
        "workflow_name": str(run.get("name", "")),
        "workflow_run_id": run_id,
        "workflow_run_url": str(run.get("html_url", "")),
    }
    return context


def main() -> None:
    repository = required_env("GITHUB_REPOSITORY")
    run_id = int(required_env("WORKFLOW_RUN_ID"))
    trigger_job_id_value = os.environ.get("TRIGGER_JOB_ID", "").strip()
    trigger_job_id = int(trigger_job_id_value) if trigger_job_id_value else None

    run = gh_api_json(f"repos/{repository}/actions/runs/{run_id}")
    if not isinstance(run, dict):
        raise SystemExit("Expected workflow run response to be a JSON object")

    jobs = gh_api_pages(f"repos/{repository}/actions/runs/{run_id}/jobs", item_key="jobs", timeout=180)
    if not all(isinstance(job, dict) for job in jobs):
        raise SystemExit("Expected workflow jobs response to contain JSON objects")

    pull_requests = run.get("pull_requests", [])
    if isinstance(pull_requests, list) and pull_requests:
        pull_request_number = int(pull_requests[0]["number"])
        pr_context = pull_request_context(repository, pull_request_number)
    else:
        pull_request_number = None
        pr_context = {}
    source_head_sha = str(pr_context.get("head_sha") or run.get("head_sha") or "")

    progress = progress_counts(jobs)  # type: ignore[arg-type]
    include_logs = run_mode(str(run.get("status", "")), run.get("conclusion"), progress["failed"]) != "progress"
    context = build_context(
        repository,
        run,
        jobs,  # type: ignore[arg-type]
        pr_context,
        pull_request_number,
        source_head_sha,
        trigger_job_id=trigger_job_id,
        include_logs=include_logs,
    )

    context_path = output_path("CI_RUN_CONTEXT_PATH", "ci-run-context.json")
    comment_body_path = output_path("COMMENT_BODY_PATH", "ci-comment-body.md")
    write_text(context_path, json.dumps(context, indent=2, sort_keys=True) + "\n")
    write_text(comment_body_path, render_progress_comment(context) + "\n")

    write_github_output("comment_body_path", comment_body_path)
    write_github_output("context_path", context_path)
    write_github_output("has_pr", "true" if pull_request_number is not None else "false")
    write_github_output("mode", str(context["mode"]))
    write_github_output("source_head_sha", source_head_sha)
    if pull_request_number is not None:
        write_github_output("pr_number", str(pull_request_number))

    print(json.dumps({"context_path": context_path, "mode": context["mode"]}, sort_keys=True))


if __name__ == "__main__":
    main()
