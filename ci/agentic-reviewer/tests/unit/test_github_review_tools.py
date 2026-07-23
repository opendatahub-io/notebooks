from __future__ import annotations

from unittest.mock import patch

import pytest

from odh_ci_agent.github_api import GitHubCommandError
from odh_ci_agent.github_review_tools import GitHubReviewClient, ReviewToolInvocation, make_github_review_tools


def test_add_comment_posts_commit_id_and_line_payload() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._pending_review_id = 99  # noqa: SLF001
    client._head_commit_id = "abc123"  # noqa: SLF001

    with patch("odh_ci_agent.github_review_tools.gh_api_json", return_value={"id": 1}) as mock_api:
        client.add_comment_to_pending_review(
            path="README.md",
            body="nit",
            subjectType="LINE",
            line=5,
            side="RIGHT",
        )

    mock_api.assert_called_once_with(
        "repos/owner/repo/pulls/12/comments",
        method="POST",
        input_json={
            "body": "nit",
            "commit_id": "abc123",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        },
    )


def test_add_comment_posts_file_subject_type() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._pending_review_id = 99  # noqa: SLF001
    client._head_commit_id = "abc123"  # noqa: SLF001

    with patch("odh_ci_agent.github_review_tools.gh_api_json", return_value={"id": 1}) as mock_api:
        client.add_comment_to_pending_review(
            path="README.md",
            body="file-level note",
            subjectType="FILE",
        )

    mock_api.assert_called_once_with(
        "repos/owner/repo/pulls/12/comments",
        method="POST",
        input_json={
            "body": "file-level note",
            "commit_id": "abc123",
            "path": "README.md",
            "subject_type": "file",
        },
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


def test_create_pending_review_reuses_existing_pending_review() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    with (
        patch(
            "odh_ci_agent.github_review_tools.gh_api_json",
            side_effect=GitHubCommandError(("gh", "api"), 422, "", "User can only have one pending review"),
        ),
        patch.object(client, "_find_pending_review_id", return_value=55) as mock_find,
    ):
        response = client.pull_request_review_write(method="create")

    mock_find.assert_called_once()
    assert response == {"id": 55, "state": "PENDING", "reused": True}
    assert client._pending_review_id == 55  # noqa: SLF001


def test_posting_failure_reason_when_all_comment_attempts_fail() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._pending_review_id = 99  # noqa: SLF001
    client._head_commit_id = "abc123"  # noqa: SLF001

    with patch(
        "odh_ci_agent.github_review_tools.gh_api_json",
        side_effect=GitHubCommandError(("gh", "api"), 422, "", "Invalid request"),
    ):
        with pytest.raises(GitHubCommandError):
            client.add_comment_to_pending_review(
                path="README.md",
                body="nit",
                subjectType="LINE",
                line=5,
            )
        with pytest.raises(GitHubCommandError):
            client.add_comment_to_pending_review(
                path="README.md",
                body="nit",
                subjectType="LINE",
                line=6,
            )

    assert client.posting_failure_reason() == "failed to post inline review comments (2 attempt(s))"


def test_posting_failure_reason_when_comments_posted_but_review_not_submitted() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.append(
        ReviewToolInvocation(tool_name="add_comment_to_pending_review", method=None, success=True)
    )

    assert client.posting_failure_reason() == "posted inline comments but never submitted the pending review"


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

    assert client.posting_failure_reason() == "posted inline comments but failed to submit the pending review"


def test_posting_failure_reason_none_when_no_comment_attempts() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    assert client.posting_failure_reason() is None


def test_make_github_review_tools_returns_client_and_tools() -> None:
    tools, client = make_github_review_tools("owner/repo", 12)

    assert len(tools) == 3
    assert client.repository == "owner/repo"
    assert client.pull_number == 12
