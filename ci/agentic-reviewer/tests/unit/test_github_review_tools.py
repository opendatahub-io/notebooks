from __future__ import annotations

from unittest.mock import call, patch

import pytest

from odh_ci_agent.github_api import GitHubCommandError
from odh_ci_agent.github_review_tools import GitHubReviewClient, ReviewToolInvocation, make_github_review_tools


def test_add_comment_stages_line_payload() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    result = client.add_comment_to_pending_review(
        path="README.md",
        body="nit",
        subjectType="LINE",
        line=5,
        side="RIGHT",
    )

    assert result == {"staged": True, "comment_count": 1}
    assert client._draft_review_comments == [  # noqa: SLF001
        {
            "body": "nit",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        }
    ]


def test_add_comment_renders_suggestion_block() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    client.add_comment_to_pending_review(
        path="README.md",
        body="Replace this branch.",
        suggestion="if flag:\n    return True",
        subjectType="LINE",
        line=5,
    )

    assert client._draft_review_comments == [  # noqa: SLF001
        {
            "body": "Replace this branch.\n\n```suggestion\nif flag:\n    return True\n```",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        }
    ]


def test_submit_pending_creates_review_with_staged_comments() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._head_commit_id = "abc123"  # noqa: SLF001

    client.add_comment_to_pending_review(
        path="README.md",
        body="nit",
        subjectType="LINE",
        line=5,
    )

    with patch(
        "odh_ci_agent.github_review_tools.gh_api_json",
        side_effect=[
            {"id": 99, "state": "PENDING"},
            {"state": "COMMENTED"},
        ],
    ) as mock_api:
        client.pull_request_review_write(method="submit_pending", event="COMMENT", body="")

    assert client._pending_review_id == 99  # noqa: SLF001
    assert client._draft_review_comments == []  # noqa: SLF001
    mock_api.assert_has_calls(
        [
            call(
                "repos/owner/repo/pulls/12/reviews",
                method="POST",
                input_json={
                    "comments": [
                        {
                            "body": "nit",
                            "path": "README.md",
                            "line": 5,
                            "side": "RIGHT",
                        }
                    ],
                    "commit_id": "abc123",
                },
            ),
            call(
                "repos/owner/repo/pulls/12/reviews/99/events",
                method="POST",
                input_json={"event": "COMMENT", "body": ""},
            ),
        ]
    )


def test_submit_pending_review_uses_events_endpoint() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._pending_review_id = 77  # noqa: SLF001

    with patch("odh_ci_agent.github_review_tools.gh_api_json", return_value={"state": "COMMENTED"}) as mock_api:
        client.pull_request_review_write(method="submit_pending", event="COMMENT", body="")

    mock_api.assert_called_once_with(
        "repos/owner/repo/pulls/12/reviews/77/events",
        method="POST",
        input_json={"event": "COMMENT", "body": ""},
    )


def test_create_pending_review_recreates_existing_pending_review_with_staged_comments() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._head_commit_id = "abc123"  # noqa: SLF001
    client.add_comment_to_pending_review(
        path="README.md",
        body="nit",
        subjectType="LINE",
        line=5,
    )

    with (
        patch.object(client, "_current_user_login", return_value="ci-bot"),
        patch(
            "odh_ci_agent.github_review_tools.gh_api_list_pages",
            return_value=[
                {
                    "id": 55,
                    "state": "PENDING",
                    "user": {"login": "ci-bot"},
                }
            ],
        ),
        patch(
            "odh_ci_agent.github_review_tools.gh_api_json",
            side_effect=[
                GitHubCommandError(
                    ("gh", "api"),
                    422,
                    '{"message":"Unprocessable Entity","errors":["User can only have one pending review per pull request"]}',
                    "gh: Unprocessable Entity (HTTP 422)",
                ),
                {},
                {"id": 77, "state": "PENDING"},
            ],
        ),
    ):
        response = client._create_pending_review(  # noqa: SLF001
            "repos/owner/repo/pulls/12",
            "owner",
            "repo",
            12,
            {},
        )

    assert response == {"id": 77, "state": "PENDING"}
    assert client._pending_review_id == 77  # noqa: SLF001
    assert client._draft_review_comments == []  # noqa: SLF001


def test_posting_failure_reason_when_all_comment_attempts_fail() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.extend(
        [
            ReviewToolInvocation(
                tool_name="add_comment_to_pending_review",
                method=None,
                success=False,
                error='GitHub CLI command failed with exit code 422: gh api\nstdout:\n\nstderr:\nInvalid request',
            ),
            ReviewToolInvocation(
                tool_name="add_comment_to_pending_review",
                method=None,
                success=False,
                error='GitHub CLI command failed with exit code 422: gh api\nstdout:\n\nstderr:\nInvalid request',
            ),
        ]
    )

    assert client.posting_failure_reason() == (
        "failed to post inline review comments (2 attempt(s)): "
        "GitHub CLI command failed with exit code 422: gh api"
    )


def test_posting_failure_reason_when_comments_posted_but_review_not_submitted() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.append(
        ReviewToolInvocation(tool_name="add_comment_to_pending_review", method=None, success=True)
    )

    assert client.posting_failure_reason() == "staged inline comments but never submitted the pending review"


def test_posting_failure_reason_when_submit_fails_after_comments_posted() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.extend(
        [
            ReviewToolInvocation(tool_name="add_comment_to_pending_review", method=None, success=True),
            ReviewToolInvocation(
                tool_name="pull_request_review_write",
                method="submit_pending",
                success=False,
                error="submit failed",
            ),
        ]
    )

    assert client.posting_failure_reason() == (
        "staged inline comments but failed to submit the pending review: submit failed"
    )


def test_posting_failure_reason_none_when_no_comment_attempts() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    assert client.posting_failure_reason() is None


def test_posting_failure_reason_when_failed_create_without_comments() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.append(
        ReviewToolInvocation(
            tool_name="pull_request_review_write",
            method="create",
            success=False,
            error='gh: Unprocessable Entity (HTTP 422)',
        )
    )

    assert client.posting_failure_reason() == (
        "GitHub review tool pull_request_review_write(create) failed: "
        "gh: Unprocessable Entity (HTTP 422)"
    )


def test_inline_comments_posted_tracks_successful_comment() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    assert client.inline_comments_posted() is False
    client.invocations.append(
        ReviewToolInvocation(tool_name="add_comment_to_pending_review", method=None, success=True)
    )
    assert client.inline_comments_posted() is False
    client.invocations.append(
        ReviewToolInvocation(tool_name="pull_request_review_write", method="submit_pending", success=True)
    )
    assert client.inline_comments_posted() is True


def test_make_github_review_tools_returns_client_and_tools() -> None:
    tools, client = make_github_review_tools("owner/repo", 12)

    assert len(tools) == 3
    assert client.repository == "owner/repo"
    assert client.pull_number == 12
    comment_tool = next(tool for tool in tools if tool.fn.__name__ == "add_comment_to_pending_review")
    review_tool = next(tool for tool in tools if tool.fn.__name__ == "pull_request_review_write")
    assert "posted to GitHub only when" in comment_tool.input_schema["description"]
    assert "submit_pending" in review_tool.input_schema["description"]
