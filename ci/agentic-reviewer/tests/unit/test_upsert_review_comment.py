from __future__ import annotations

from odh_ci_agent import upsert_review_comment


def test_latest_prior_summary_comment_returns_latest_non_current() -> None:
    comments = [
        {"id": 1, "body": "<!-- antigravity-pr-review run_id=10 --> old"},
        {"id": 2, "body": "<!-- antigravity-pr-review run_id=11 --> newer"},
        {"id": 3, "body": "<!-- antigravity-pr-review run_id=12 --> current"},
    ]

    prior = upsert_review_comment.latest_prior_summary_comment(comments, run_id=12)

    assert prior is not None
    assert prior["id"] == 2


def test_latest_matching_run_comment_returns_newest_duplicate() -> None:
    comments = [
        {
            "id": 1,
            "body": "<!-- antigravity-pr-review run_id=99 updated_at=2026-06-05T10:00:00Z --> old",
            "created_at": "2026-06-05T10:00:00Z",
        },
        {
            "id": 2,
            "body": "<!-- antigravity-pr-review run_id=99 updated_at=2026-06-05T11:00:00Z --> new",
            "created_at": "2026-06-05T11:00:00Z",
            "updated_at": "2026-06-05T11:00:00Z",
        },
    ]

    match = upsert_review_comment.latest_matching_run_comment(comments, run_id=99)

    assert match is not None
    assert match["id"] == 2
