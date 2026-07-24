"""Shared helpers for Antigravity CI summary workflows."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

SUMMARY_MARKER_PREFIX = "antigravity-ci-summary"
MAX_RUNNING_JOBS_IN_COMMENT = 10

OOM_PATTERNS = ("Killed process", "exit 137", "out of memory", "oom")
HERMETO_PATTERNS = ("cachi2", "hermetic build", "prefetch", "hermeto")
TRIVY_PATTERNS = ("trivy", "vulnerability scanner")
FIPS_PATTERNS = ("check-payload", "fips")
PLAYWRIGHT_PATTERNS = ("playwright",)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def marker_for_run(run_id: int, *, failed_jobs: int, updated_at: str | None = None) -> str:
    timestamp = updated_at or utc_now_iso()
    return f"<!-- {SUMMARY_MARKER_PREFIX} run_id={run_id} updated_at={timestamp} failed_jobs={failed_jobs} -->"


def marker_token(run_id: int) -> str:
    return f"<!-- {SUMMARY_MARKER_PREFIX} run_id={run_id} "


def int_value(value: object) -> int:
    """Convert a JSON-like value to int with a clearer failure surface."""

    if isinstance(value, bool):
        raise TypeError("Boolean is not a valid integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")


def cluster_failed_job(failed_step: str, log_tail: str) -> str:
    haystack = f"{failed_step}\n{log_tail}".lower()
    if any(pattern.lower() in haystack for pattern in OOM_PATTERNS):
        return "oom_or_killed"
    if any(pattern.lower() in haystack for pattern in HERMETO_PATTERNS):
        return "hermeto_prefetch"
    if any(pattern.lower() in haystack for pattern in TRIVY_PATTERNS):
        return "trivy_scan"
    if any(pattern.lower() in haystack for pattern in FIPS_PATTERNS):
        return "fips_check"
    if any(pattern.lower() in haystack for pattern in PLAYWRIGHT_PATTERNS):
        return "playwright"
    if "make " in haystack or failed_step.startswith("Build: make "):
        return "make_build"
    return "other"


def escape_markdown_table_cell(value: object) -> str:
    """Escape untrusted text for markdown table cells."""

    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    return text.replace("|", "\\|").replace("`", "\\`")


def string_list(value: object) -> list[str]:
    """Normalize a JSON-like field back into a list of strings."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def build_clusters(failed_jobs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for failed_job in failed_jobs:
        error_contexts = string_list(failed_job.get("error_contexts"))
        joined_error_contexts = "\n\n".join(error_contexts)
        pattern = cluster_failed_job(
            str(failed_job.get("failed_step", "")),
            "\n\n".join(
                part
                for part in (
                    str(failed_job.get("log_excerpt") or failed_job.get("log_tail", "")),
                    joined_error_contexts,
                )
                if part
            ),
        )
        grouped[pattern].append(str(failed_job.get("name", "")))

    return [
        {"pattern": pattern, "jobs": sorted(job_names)}
        for pattern, job_names in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def summarize_progress(progress: Mapping[str, int]) -> str:
    total = progress.get("total", 0)
    completed = progress.get("completed", 0)
    passed = progress.get("passed", 0)
    failed = progress.get("failed", 0)
    running = progress.get("in_progress", 0)
    cancelled = progress.get("cancelled", 0)
    skipped = progress.get("skipped", 0)

    summary = f"**{completed}/{total} complete**"
    if passed:
        summary += f" · {passed} passed"
    if failed:
        summary += f" · {failed} failed"
    if skipped:
        summary += f" · {skipped} skipped"
    if running:
        summary += f" · {running} running"
    if cancelled:
        summary += f" · {cancelled} cancelled"
    if not failed and not running and not cancelled and completed == total and not skipped:
        summary = f"**{passed}/{total} passed**"
    return summary


def render_progress_comment(context: Mapping[str, object]) -> str:
    workflow_name = str(context["workflow_name"])
    run_url = str(context["workflow_run_url"])
    run_id = int_value(context["workflow_run_id"])
    progress = context["progress"]
    if not isinstance(progress, Mapping):
        raise TypeError("context['progress'] must be a mapping")

    triggered_job = str(context.get("trigger_job_name", "workflow update")).strip() or "workflow update"
    updated_at = str(context.get("updated_at", utc_now_iso()))
    failed_jobs = context.get("failed_jobs", [])
    if not isinstance(failed_jobs, list):
        raise TypeError("context['failed_jobs'] must be a list")
    in_progress_jobs = context.get("in_progress_jobs", [])
    if not isinstance(in_progress_jobs, list):
        raise TypeError("context['in_progress_jobs'] must be a list")

    lines = [
        "## CI status [antigravity]",
        "",
        f"**Run:** [{workflow_name} #{run_id}]({run_url}) — {summarize_progress(progress)}",
        f"_Last updated: {updated_at} after `{html.escape(triggered_job)}` completed_",
        "",
    ]

    if failed_jobs:
        lines.extend(
            [
                "### Failures so far",
                "| Job | Failed step | Link |",
                "| --- | --- | --- |",
            ]
        )
        for failed_job in failed_jobs:
            job_name = escape_markdown_table_cell(failed_job.get("name", ""))
            failed_step = escape_markdown_table_cell(failed_job.get("failed_step", ""))
            url = str(failed_job.get("url", ""))
            lines.append(f"| {job_name} | {failed_step} | [logs]({url}) |")
        lines.append("")

    if in_progress_jobs:
        lines.append("### Still running")
        for job_name in in_progress_jobs[:MAX_RUNNING_JOBS_IN_COMMENT]:
            lines.append(f"- `{job_name}`")
        remaining = len(in_progress_jobs) - MAX_RUNNING_JOBS_IN_COMMENT
        if remaining > 0:
            lines.append(f"- `... and {remaining} more`")
        lines.append("")

    lines.append(marker_for_run(run_id, failed_jobs=int(progress.get("failed", 0)), updated_at=updated_at))
    return "\n".join(lines)


def render_failed_jobs_table(failed_jobs: Sequence[Mapping[str, object]], *, max_rows: int = 8) -> list[str]:
    """Render a bounded failed-jobs markdown table."""

    lines = [
        "### Failures so far",
        "| Job | Failed step | Link |",
        "| --- | --- | --- |",
    ]
    for failed_job in failed_jobs[:max_rows]:
        job_name = escape_markdown_table_cell(failed_job.get("name", ""))
        failed_step = escape_markdown_table_cell(failed_job.get("failed_step", ""))
        url = str(failed_job.get("url", ""))
        lines.append(f"| {job_name} | {failed_step} | [logs]({url}) |")
    remaining = len(failed_jobs) - max_rows
    if remaining > 0:
        lines.extend(["", f"*(+ {remaining} other failed matrix jobs)*"])
    return lines


def render_running_jobs_section(in_progress_jobs: Sequence[object]) -> list[str]:
    """Render the bounded in-progress job list."""

    if not in_progress_jobs:
        return []
    lines = ["### Still running"]
    for job_name in in_progress_jobs[:MAX_RUNNING_JOBS_IN_COMMENT]:
        lines.append(f"- `{job_name}`")
    remaining = len(in_progress_jobs) - MAX_RUNNING_JOBS_IN_COMMENT
    if remaining > 0:
        lines.append(f"- `... and {remaining} more`")
    return lines


def render_final_success_comment(context: Mapping[str, object]) -> str:
    """Render a concise deterministic comment for an all-green completed run."""

    workflow_name = str(context["workflow_name"])
    run_url = str(context["workflow_run_url"])
    run_id = int_value(context["workflow_run_id"])
    progress = context["progress"]
    if not isinstance(progress, Mapping):
        raise TypeError("context['progress'] must be a mapping")
    matrix_progress = context.get("matrix_progress", {})
    if not isinstance(matrix_progress, Mapping):
        raise TypeError("context['matrix_progress'] must be a mapping")

    updated_at = str(context.get("updated_at", utc_now_iso()))
    skipped = int(progress.get("skipped", 0))
    passed = int(progress.get("passed", 0))
    matrix_total = int(matrix_progress.get("total", 0))
    matrix_skipped = int(matrix_progress.get("skipped", 0))
    matrix_passed = int(matrix_progress.get("passed", 0))

    if matrix_total > 0 and matrix_skipped == matrix_total and matrix_passed == 0:
        final_line = "_No workbench image jobs ran; all matrix jobs were skipped._"
    elif skipped:
        final_line = "_Workflow completed with skipped jobs._"
    elif passed == 0:
        final_line = "_Workflow completed without any passing jobs._"
    else:
        final_line = "_All matrix jobs completed successfully._"

    lines = [
        "## CI status [antigravity]",
        "",
        f"**Run:** [{workflow_name} #{run_id}]({run_url}) — {summarize_progress(progress)}",
        f"_Last updated: {updated_at}_",
        "",
        final_line,
        "",
        marker_for_run(run_id, failed_jobs=int(progress.get("failed", 0)), updated_at=updated_at),
    ]
    return "\n".join(lines)


def render_failure_comment(context: Mapping[str, object], analysis_markdown: str) -> str:
    """Render a deterministic failure comment with LLM-generated analysis only."""

    workflow_name = str(context["workflow_name"])
    run_url = str(context["workflow_run_url"])
    run_id = int_value(context["workflow_run_id"])
    progress = context["progress"]
    if not isinstance(progress, Mapping):
        raise TypeError("context['progress'] must be a mapping")
    failed_jobs = context.get("failed_jobs", [])
    if not isinstance(failed_jobs, list):
        raise TypeError("context['failed_jobs'] must be a list")
    in_progress_jobs = context.get("in_progress_jobs", [])
    if not isinstance(in_progress_jobs, list):
        raise TypeError("context['in_progress_jobs'] must be a list")

    updated_at = str(context.get("updated_at", utc_now_iso()))
    triggered_job = str(context.get("trigger_job_name", "workflow update")).strip() or "workflow update"

    lines = [
        "## CI status [antigravity]",
        "",
        f"**Run:** [{workflow_name} #{run_id}]({run_url}) — {summarize_progress(progress)}",
        f"_Last updated: {updated_at} after `{html.escape(triggered_job)}` completed_",
        "",
        *render_failed_jobs_table(failed_jobs),
    ]

    running_section = render_running_jobs_section(in_progress_jobs)
    if running_section:
        lines.extend(["", *running_section])

    analysis = analysis_markdown.strip()
    if analysis:
        lines.extend(["", analysis])

    lines.extend(
        [
            "",
            marker_for_run(run_id, failed_jobs=int(progress.get("failed", 0)), updated_at=updated_at),
        ]
    )
    return "\n".join(lines)


def render_superseded_comment(existing_body: str, *, new_run_url: str) -> str:
    if "Superseded by newer run:" in existing_body:
        return existing_body
    return f"> Superseded by newer run: {new_run_url}\n\n{existing_body}"


def comment_contains_run_marker(body: str, run_id: int) -> bool:
    return marker_token(run_id) in body


def find_all_run_markers(body: str) -> list[int]:
    return [int(match.group(1)) for match in re.finditer(rf"{SUMMARY_MARKER_PREFIX} run_id=(\d+)", body)]
