from __future__ import annotations

from odh_ci_agent import pr_review_summary


def test_extract_review_summary_body_returns_default_when_missing_header() -> None:
    body = pr_review_summary.extract_review_summary_body("Review complete.")

    assert body.startswith("## 📋 Review Summary")
    assert "inline comments" in body


def test_extract_review_summary_body_keeps_summary_sections() -> None:
    text = (
        "Done.\n\n"
        "## 📋 Review Summary\n\n"
        "Looks good overall.\n\n"
        "## 🔍 General Feedback\n\n"
        "- Consider adding a test.\n\n"
        "Posted a review with 2 inline comments."
    )

    body = pr_review_summary.extract_review_summary_body(text)

    assert "Looks good overall." in body
    assert "## 🔍 General Feedback" in body
    assert "Consider adding a test." in body
    assert "Posted a review" not in body


def test_ensure_marker_appends_once() -> None:
    marker = pr_review_summary.marker_for_run(42)

    first = pr_review_summary.ensure_marker("hello", marker, run_id=42)
    second = pr_review_summary.ensure_marker(first, marker, run_id=42)

    assert marker in first
    assert first == second
