from __future__ import annotations

from unittest.mock import patch

from odh_ci_agent.github_api import GitHubCommandError
from odh_ci_agent.pr_review_summary import (
    is_active_review_summary_comment,
    is_antigravity_review_summary_comment,
    is_superseded_comment,
    marker_for_run,
)
from odh_ci_agent.upsert_review_comment import (
    latest_review_summary_comment,
    other_active_review_summary_comments,
    supersede_review_summary_comments,
)

AUTHOR_LOGIN = "github-actions[bot]"


def _comment(
    comment_id: int,
    body: str,
    *,
    updated_at: str = "2026-01-02T00:00:00Z",
    login: str = AUTHOR_LOGIN,
) -> dict[str, object]:
    return {"id": comment_id, "body": body, "updated_at": updated_at, "user": {"login": login}}


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

    latest = latest_review_summary_comment(comments, author_login=AUTHOR_LOGIN)

    assert latest is not None
    assert latest["id"] == 2


def test_latest_review_summary_comment_picks_newest_summary_comment() -> None:
    comments = [
        _comment(1, f"## Summary\n\n{marker_for_run(10)}", updated_at="2026-01-01T00:00:00Z"),
        _comment(2, f"## Summary\n\n{marker_for_run(11)}", updated_at="2026-01-03T00:00:00Z"),
    ]

    latest = latest_review_summary_comment(comments, author_login=AUTHOR_LOGIN)

    assert latest is not None
    assert latest["id"] == 2


def test_latest_review_summary_comment_ignores_coderabbit_without_marker() -> None:
    coderabbit_body = (
        "## 📋 Review Summary\n\nMentions `.github/workflows/antigravity-pr-review.yml` but is not ours.\n"
    )
    ours = f"## 📋 Review Summary\n\nAntigravity summary.\n\n{marker_for_run(12)}"
    comments = [
        _comment(1, coderabbit_body, updated_at="2026-01-05T00:00:00Z", login="coderabbitai[bot]"),
        _comment(2, ours, updated_at="2026-01-01T00:00:00Z"),
    ]

    latest = latest_review_summary_comment(comments, author_login=AUTHOR_LOGIN)

    assert latest is not None
    assert latest["id"] == 2


def test_latest_review_summary_comment_ignores_coderabbit_even_with_marker() -> None:
    marker = marker_for_run(13)
    coderabbit = _comment(
        1,
        f"## 📋 Review Summary\n\nCodeRabbit text.\n\n{marker}",
        updated_at="2026-01-05T00:00:00Z",
        login="coderabbitai[bot]",
    )
    ours = _comment(
        2,
        f"## 📋 Review Summary\n\nAntigravity summary.\n\n{marker_for_run(14)}",
        updated_at="2026-01-01T00:00:00Z",
    )

    latest = latest_review_summary_comment([coderabbit, ours], author_login=AUTHOR_LOGIN)

    assert latest is not None
    assert latest["id"] == 2


def test_other_active_review_summary_comments_excludes_kept_comment() -> None:
    body_a = f"## Summary\n\n{marker_for_run(10)}"
    body_b = f"## Summary\n\n{marker_for_run(11)}"
    comments = [_comment(1, body_a), _comment(2, body_b)]

    others = other_active_review_summary_comments(comments, author_login=AUTHOR_LOGIN, keep_comment_id=2)

    assert len(others) == 1
    assert others[0]["id"] == 1


def test_is_active_review_summary_comment() -> None:
    marker = marker_for_run(42)
    active_body = f"## 📋 Review Summary\n\nLooks good.\n\n{marker}"
    superseded_body = f"> Superseded by newer run: https://example.com\n\n{active_body}"

    assert is_active_review_summary_comment(active_body) is True
    assert is_superseded_comment(superseded_body) is True
    assert is_active_review_summary_comment(superseded_body) is False


def test_is_antigravity_review_summary_comment_requires_matching_author() -> None:
    marker = marker_for_run(42)
    comment = {
        "body": f"## 📋 Review Summary\n\n{marker}",
        "user": {"login": "coderabbitai[bot]"},
    }

    assert is_antigravity_review_summary_comment(comment, author_login=AUTHOR_LOGIN) is False
    assert is_antigravity_review_summary_comment(comment, author_login="coderabbitai[bot]") is True


def test_supersede_review_summary_comments_continues_after_patch_failure() -> None:
    marker = marker_for_run(10)
    comments = [
        _comment(1, f"## Summary\n\n{marker}"),
        _comment(2, f"## Summary\n\n{marker_for_run(11)}"),
        _comment(3, f"## Summary\n\n{marker_for_run(12)}"),
    ]

    with patch(
        "odh_ci_agent.upsert_review_comment.gh_api_json",
        side_effect=[
            GitHubCommandError(("gh", "api"), 404, "", "not found"),
            {"id": 3},
        ],
    ) as mock_api:
        supersede_review_summary_comments(
            comments,
            author_login=AUTHOR_LOGIN,
            repository="owner/repo",
            keep_comment_id=2,
            workflow_run_url="https://example.com/run/3",
        )

    assert mock_api.call_count == 2
