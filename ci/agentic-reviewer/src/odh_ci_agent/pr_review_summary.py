"""Shared helpers for Antigravity PR review summary issue comments."""

from __future__ import annotations

from odh_ci_agent.ci_summary import utc_now_iso

REVIEW_SUMMARY_MARKER_PREFIX = "antigravity-pr-review"
REVIEW_SUMMARY_HEADER = "## 📋 Review Summary"


def marker_for_run(run_id: int, *, updated_at: str | None = None) -> str:
    timestamp = updated_at or utc_now_iso()
    return f"<!-- {REVIEW_SUMMARY_MARKER_PREFIX} run_id={run_id} updated_at={timestamp} -->"


def marker_token(run_id: int) -> str:
    return f"<!-- {REVIEW_SUMMARY_MARKER_PREFIX} run_id={run_id} "


def comment_contains_run_marker(body: str, run_id: int) -> bool:
    return marker_token(run_id) in body


def ensure_marker(body: str, marker: str, *, run_id: int) -> str:
    if marker_token(run_id) in body:
        return body
    return f"{body}\n\n{marker}"


def extract_review_summary_body(text: str) -> str:
    """Return markdown for the upserted review summary comment."""

    if REVIEW_SUMMARY_HEADER not in text:
        return f"{REVIEW_SUMMARY_HEADER}\n\nAutomated review completed. See inline comments for findings.\n"

    excerpt = text[text.index(REVIEW_SUMMARY_HEADER) :].strip()
    cleaned_lines: list[str] = []
    for line in excerpt.splitlines():
        normalized = line.strip().lower()
        if normalized.startswith(("posted a review", "i posted a review", "review posted")):
            break
        cleaned_lines.append(line)
    body = "\n".join(cleaned_lines).strip()
    return body or (f"{REVIEW_SUMMARY_HEADER}\n\nAutomated review completed. See inline comments for findings.\n")
