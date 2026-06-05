#!/usr/bin/env python3
"""Prepare bounded CI context for the Antigravity matrix-build summarizer."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence

from scripts.ci.ci_summary import build_clusters, int_value, marker_for_run, render_progress_comment, utc_now_iso
from scripts.ci.github_api import gh_api_json, gh_api_pages, gh_run_job_log

MAX_LOG_LINES = 150
MAX_LOG_CHARS = 12_000
MAX_FAILED_JOBS_WITH_LOGS = 15


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def output_path(env_name: str, default_name: str) -> str:
    return os.environ.get(env_name, default_name)


def failed_step_name(job: Mapping[str, object]) -> str:
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        return "Unknown step"

    failed_steps = [
        str(step.get("name", "Unknown step"))
        for step in steps
        if isinstance(step, Mapping) and step.get("conclusion") in {"failure", "cancelled"}
    ]
    if failed_steps:
        return failed_steps[-1]

    in_progress_steps = [
        str(step.get("name", "Unknown step"))
        for step in steps
        if isinstance(step, Mapping) and step.get("status") == "in_progress"
    ]
    if in_progress_steps:
        return in_progress_steps[-1]

    return "Unknown step"


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


def bounded_log_tail(run_id: int, job_id: int) -> tuple[str, str]:
    try:
        log_text = gh_run_job_log(run_id, job_id, timeout=180)
    except Exception as exc:  # noqa: BLE001
        return "", f"{type(exc).__name__}: {exc}"

    lines = log_text.splitlines()
    tail = "\n".join(lines[-MAX_LOG_LINES:])
    if len(tail) > MAX_LOG_CHARS:
        tail = tail[-MAX_LOG_CHARS:]
    return tail, ""


def build_failed_jobs(run_id: int, jobs: Sequence[Mapping[str, object]], *, include_logs: bool) -> list[dict[str, object]]:
    failed_jobs: list[dict[str, object]] = []
    for index, job in enumerate(jobs):
        if job.get("conclusion") not in {"failure", "cancelled"}:
            continue

        log_tail = ""
        log_error = ""
        if include_logs and len(failed_jobs) < MAX_FAILED_JOBS_WITH_LOGS:
            log_tail, log_error = bounded_log_tail(run_id, int_value(job["id"]))

        failed_jobs.append(
            {
                "id": int_value(job["id"]),
                "name": str(job.get("name", "")),
                "failed_step": failed_step_name(job),
                "conclusion": str(job.get("conclusion", "")),
                "index": index,
                "log_error": log_error or None,
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
