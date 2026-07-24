from __future__ import annotations

from odh_ci_agent.pr_review_summary import (
    is_active_review_summary_comment,
    is_superseded_comment,
    marker_for_run,
)
from odh_ci_agent.upsert_review_comment import (
    latest_review_summary_comment,
    other_active_review_summary_comments,
)


def _comment(comment_id: int, body: str, *, updated_at: str = "2026-01-02T00:00:00Z") -> dict[str, object]:
    return {"id": comment_id, "body": body, "updated_at": updated_at}


def test_latest_review_summary_comment_reuses_latest_even_if_superseded() -> None:
    marker = marker_for_run(100)
    comments = [
        _comment(1, f"## Summary\n\n{marker}", updated_at="2026-01-01T00:00:00Z"),
        _comment(
            2,
            f"> Superseded by newer run: https://example.com\n\n## Summary\n\n{marker_for_run(99)}",
            updated_at="2026-01-03T00:00:00Z",
        ),
    ]

    latest = latest_review_summary_comment(comments)

    assert latest is not None
    assert latest["id"] == 2


def test_latest_review_summary_comment_picks_newest_summary_comment() -> None:
    comments = [
        _comment(1, f"## Summary\n\n{marker_for_run(10)}", updated_at="2026-01-01T00:00:00Z"),
        _comment(2, f"## Summary\n\n{marker_for_run(11)}", updated_at="2026-01-03T00:00:00Z"),
    ]

    latest = latest_review_summary_comment(comments)

    assert latest is not None
    assert latest["id"] == 2


def test_other_active_review_summary_comments_excludes_kept_comment() -> None:
    body_a = f"## Summary\n\n{marker_for_run(10)}"
    body_b = f"## Summary\n\n{marker_for_run(11)}"
    comments = [_comment(1, body_a), _comment(2, body_b)]

    others = other_active_review_summary_comments(comments, keep_comment_id=2)

    assert len(others) == 1
    assert others[0]["id"] == 1


def test_is_active_review_summary_comment() -> None:
    marker = marker_for_run(42)
    active_body = f"## 📋 Review Summary\n\nLooks good.\n\n{marker}"
    superseded_body = f"> Superseded by newer run: https://example.com\n\n{active_body}"

    assert is_active_review_summary_comment(active_body) is True
    assert is_superseded_comment(superseded_body) is True
    assert is_active_review_summary_comment(superseded_body) is False
