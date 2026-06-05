#!/usr/bin/env python3
"""Prepare bounded CI context for the Antigravity matrix-build summarizer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence

from scripts.ci.ci_summary import build_clusters, int_value, marker_for_run, render_progress_comment, utc_now_iso
from scripts.ci.github_api import gh_api_json, gh_api_pages, gh_run_job_log

MAX_LOG_LINES = 150
MAX_LOG_CHARS = 12_000
MAX_FAILED_JOBS_WITH_LOGS = 15
FAILED_STEP_CONTEXT_BEFORE = 10
FAILED_STEP_CONTEXT_AFTER = 40
FAILED_STEP_ERROR_TAIL_BEFORE = 10
FAILED_STEP_ERROR_TAIL_AFTER = 5

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
        step
        for step in steps
        if isinstance(step, Mapping) and step.get("conclusion") in {"failure", "cancelled"}
    ]
    if failed_steps:
        return failed_steps[-1]

    in_progress_steps = [
        step
        for step in steps
        if isinstance(step, Mapping) and step.get("status") == "in_progress"
    ]
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
        "failed": 0,
        "cancelled": 0,
        "in_progress": 0,
        "queued": 0,
    }
    for job in jobs:
        status = str(job.get("status", ""))
        conclusion = job.get("conclusion")
        if status == "completed":
            counts["completed"] += 1
            if conclusion == "failure":
                counts["failed"] += 1
            elif conclusion == "cancelled":
                counts["cancelled"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
        else:
            counts["queued"] += 1
    return counts


def parse_iso8601_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
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
        stripped.startswith("Error:")
        or stripped.startswith("ERROR ")
        or stripped.startswith("Exception:")
        or stripped.startswith("Traceback (most recent call last):")
        or stripped.startswith("FAILED ")
        or stripped.startswith("SUBFAILED")
        or "permission denied" in lowered
        or "fetcherror" in lowered
        or "no module named" in lowered
        or "=> not found" in lowered
        or "unsatisfied dependencies" in lowered
        or "make: ***" in lowered
        or "assert " in lowered
    )


def clip_excerpt(lines: Sequence[str]) -> str:
    excerpt = "\n".join(lines)
    if len(excerpt) <= MAX_LOG_CHARS:
        return excerpt

    head_keep = max(1, len(lines) // 3)
    tail_keep = max(1, len(lines) // 3)
    clipped = list(lines[:head_keep]) + ["..."] + list(lines[-tail_keep:])
    excerpt = "\n".join(clipped)
    if len(excerpt) <= MAX_LOG_CHARS:
        return excerpt
    return excerpt[-MAX_LOG_CHARS:]


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
        step_end = step_end + timedelta(seconds=2)

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
    excerpt_lines = step_lines[max(0, first_anchor - FAILED_STEP_CONTEXT_BEFORE) : min(
        len(step_lines),
        first_anchor + FAILED_STEP_CONTEXT_AFTER,
    )]

    if last_anchor > first_anchor + FAILED_STEP_CONTEXT_AFTER:
        tail_start = max(0, last_anchor - FAILED_STEP_ERROR_TAIL_BEFORE)
        tail_end = min(len(step_lines), last_anchor + FAILED_STEP_ERROR_TAIL_AFTER)
        excerpt_lines = [*excerpt_lines, "...", *step_lines[tail_start:tail_end]]

    return clip_excerpt(excerpt_lines)


def fetch_job_log(run_id: int, job_id: int) -> tuple[str, str]:
    try:
        log_text = gh_run_job_log(run_id, job_id, timeout=180)
    except Exception as exc:  # noqa: BLE001
        return "", f"{type(exc).__name__}: {exc}"

    return log_text, ""


def build_failed_jobs(run_id: int, jobs: Sequence[Mapping[str, object]], *, include_logs: bool) -> list[dict[str, object]]:
    failed_jobs: list[dict[str, object]] = []
    for index, job in enumerate(jobs):
        if job.get("conclusion") not in {"failure", "cancelled"}:
            continue

        log_tail = ""
        log_excerpt = ""
        log_error = ""
        if include_logs and len(failed_jobs) < MAX_FAILED_JOBS_WITH_LOGS:
            job_log, log_error = fetch_job_log(run_id, int_value(job["id"]))
            if not log_error:
                log_excerpt = failed_step_excerpt(job_log, job)
                log_tail = log_excerpt

        failed_jobs.append(
            {
                "id": int_value(job["id"]),
                "name": str(job.get("name", "")),
                "failed_step": failed_step_name(job),
                "conclusion": str(job.get("conclusion", "")),
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


def build_context(
    repository: str,
    run: Mapping[str, object],
    jobs: Sequence[Mapping[str, object]],
    *,
    trigger_job_id: int | None,
    include_logs: bool,
) -> dict[str, object]:
    progress = progress_counts(jobs)
    run_status = str(run.get("status", ""))
    raw_conclusion = run.get("conclusion")
    run_conclusion = str(raw_conclusion) if raw_conclusion else None
    mode = run_mode(run_status, run_conclusion, progress["failed"])
    run_id = int_value(run["id"])
    failed_jobs = build_failed_jobs(run_id, jobs, include_logs=include_logs)
    in_progress_jobs = [
        str(job.get("name", ""))
        for job in jobs
        if job.get("status") != "completed"
    ]

    trigger_job_name = "workflow update"
    if trigger_job_id is not None:
        for job in jobs:
            if int_value(job["id"]) == trigger_job_id:
                trigger_job_name = str(job.get("name", trigger_job_name))
                break

    pull_requests = run.get("pull_requests", [])
    if not isinstance(pull_requests, list) or not pull_requests:
        raise SystemExit("Workflow run has no associated pull request; summary workflow only supports PR runs")

    pull_request_number = int(pull_requests[0]["number"])
    updated_at = utc_now_iso()
    context: dict[str, object] = {
        "comment_marker": marker_for_run(run_id, failed_jobs=progress["failed"], updated_at=updated_at),
        "clusters": build_clusters(failed_jobs),
        "failed_jobs": failed_jobs,
        "github_repository": repository,
        "in_progress_jobs": in_progress_jobs,
        "mode": mode,
        "pr_number": pull_request_number,
        "progress": progress,
        "run_conclusion": run_conclusion,
        "run_status": run_status,
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

    progress = progress_counts(jobs)  # type: ignore[arg-type]
    include_logs = run_mode(str(run.get("status", "")), run.get("conclusion"), progress["failed"]) != "progress"
    context = build_context(
        repository,
        run,
        jobs,  # type: ignore[arg-type]
        trigger_job_id=trigger_job_id,
        include_logs=include_logs,
    )

    context_path = output_path("CI_RUN_CONTEXT_PATH", "ci-run-context.json")
    comment_body_path = output_path("COMMENT_BODY_PATH", "ci-comment-body.md")
    write_text(context_path, json.dumps(context, indent=2, sort_keys=True) + "\n")
    write_text(comment_body_path, render_progress_comment(context) + "\n")

    write_github_output("comment_body_path", comment_body_path)
    write_github_output("context_path", context_path)
    write_github_output("mode", str(context["mode"]))

    print(json.dumps({"context_path": context_path, "mode": context["mode"]}, sort_keys=True))


if __name__ == "__main__":
    main()
