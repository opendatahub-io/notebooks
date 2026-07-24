from __future__ import annotations

from odh_ci_agent import upsert_ci_comment


def test_ensure_marker_appends_once() -> None:
    marker = "<!-- antigravity-ci-summary run_id=99 updated_at=2026-06-05T00:00:00Z failed_jobs=1 -->"

    body = upsert_ci_comment.ensure_marker("hello", marker, run_id=99)
    body_again = upsert_ci_comment.ensure_marker(body, marker, run_id=99)

    assert body.endswith(marker)
    assert body == body_again


def test_latest_prior_summary_comment_returns_latest_non_current() -> None:
    comments = [
        {"id": 1, "body": "<!-- antigravity-ci-summary run_id=10 --> old"},
        {"id": 2, "body": "<!-- antigravity-ci-summary run_id=11 --> newer"},
        {"id": 3, "body": "<!-- antigravity-ci-summary run_id=12 --> current"},
    ]

    prior = upsert_ci_comment.latest_prior_summary_comment(comments, run_id=12)

    assert prior is not None
    assert prior["id"] == 2
