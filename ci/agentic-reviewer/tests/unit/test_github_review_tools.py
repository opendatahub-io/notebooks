from __future__ import annotations

from unittest.mock import call, patch

from odh_ci_agent.github_api import GitHubCommandError
from odh_ci_agent.github_review_tools import GitHubReviewClient, ReviewToolInvocation, make_github_review_tools
from odh_ci_agent.review_diff_lines import DiffLineIndex


def _stub_diff_index(*paths: tuple[str, set[int]]) -> DiffLineIndex:
    return DiffLineIndex(right=dict(paths), left={})


def _patch_diff_index(client: GitHubReviewClient, index: DiffLineIndex):
    return patch.object(client, "_load_diff_line_index", return_value=index)


def test_with_pr_defaults_pins_bound_repository() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    with patch("odh_ci_agent.github_review_tools.gh_api_json", return_value={"number": 12}) as mock_api:
        client.pull_request_read(method="get", owner="evil", repo="other", pullNumber=999)

    mock_api.assert_called_once_with("repos/owner/repo/pulls/12")


def test_add_comment_stages_line_payload() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
        result = client.add_comment_to_pending_review(
            path="README.md",
            body="nit",
            subjectType="LINE",
            line=5,
            side="RIGHT",
        )

    assert result == {"staged": True, "comment_count": 1}
    assert client._draft_review_comments == [
        {
            "body": "nit",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        }
    ]


def test_add_comment_renders_suggestion_block() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
        client.add_comment_to_pending_review(
            path="README.md",
            body="Replace this branch.",
            suggestion="if flag:\n    return True",
            subjectType="LINE",
            line=5,
        )

    assert client._draft_review_comments == [
        {
            "body": "Replace this branch.\n\n```suggestion\nif flag:\n    return True\n```",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        }
    ]


def test_submit_pending_creates_review_with_staged_comments() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._head_commit_id = "abc123"

    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
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

    assert client._pending_review_id == 99
    assert client._draft_review_comments == []
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
    client._pending_review_id = 77

    with patch("odh_ci_agent.github_review_tools.gh_api_json", return_value={"state": "COMMENTED"}) as mock_api:
        client.pull_request_review_write(method="submit_pending", event="COMMENT", body="summary")

    mock_api.assert_called_once_with(
        "repos/owner/repo/pulls/12/reviews/77/events",
        method="POST",
        input_json={"event": "COMMENT", "body": "summary"},
    )


def test_submit_pending_skips_empty_review_without_api_call() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    with patch("odh_ci_agent.github_review_tools.gh_api_json") as mock_api:
        result = client.pull_request_review_write(method="submit_pending", event="COMMENT", body="")

    assert result == {"skipped": True, "reason": "no review comments or body to submit"}
    mock_api.assert_not_called()
    assert client.invocations == []
    assert client.review_outcome()["review_submitted"] is False


def test_submit_pending_coerces_request_changes_to_comment() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._pending_review_id = 77

    with patch("odh_ci_agent.github_review_tools.gh_api_json", return_value={"state": "COMMENTED"}) as mock_api:
        client.pull_request_review_write(
            method="submit_pending",
            event="REQUEST_CHANGES",
            body="Please address the inline comments.",
        )

    mock_api.assert_called_once_with(
        "repos/owner/repo/pulls/12/reviews/77/events",
        method="POST",
        input_json={"event": "COMMENT", "body": "Please address the inline comments."},
    )


def test_posting_failure_reason_ignores_failed_submit_when_later_submit_succeeds() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.extend(
        [
            ReviewToolInvocation(
                tool_name="pull_request_review_write",
                method="submit_pending",
                success=False,
                error='{"errors":["Could not comment for pull request review."]}',
            ),
            ReviewToolInvocation(
                tool_name="pull_request_review_write",
                method="submit_pending",
                success=True,
            ),
        ]
    )

    assert client.posting_failure_reason() is None


def test_create_pending_review_recreates_existing_pending_review_with_staged_comments() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._head_commit_id = "abc123"
    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
        client.add_comment_to_pending_review(
            path="README.md",
            body="nit",
            subjectType="LINE",
            line=5,
        )

    with (
        _patch_diff_index(client, _stub_diff_index(("README.md", {5}))),
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
        response = client._create_pending_review(
            "repos/owner/repo/pulls/12",
            "owner",
            "repo",
            12,
            {},
        )

    assert response == {"id": 77, "state": "PENDING"}
    assert client._pending_review_id == 77
    assert client._draft_review_comments == []


def test_find_pending_review_id_falls_back_to_single_bot_review_when_user_lookup_is_denied() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    with (
        patch(
            "odh_ci_agent.github_review_tools.gh_api_json",
            side_effect=GitHubCommandError(
                ("gh", "api"),
                403,
                '{"message":"Resource not accessible by integration","status":"403"}',
                "gh: Resource not accessible by integration (HTTP 403)",
            ),
        ),
        patch(
            "odh_ci_agent.github_review_tools.gh_api_list_pages",
            return_value=[
                {
                    "id": 55,
                    "state": "PENDING",
                    "user": {"login": "github-actions[bot]"},
                }
            ],
        ),
    ):
        review_id = client._find_pending_review_id("owner", "repo", 12)

    assert review_id == 55


def test_posting_failure_reason_when_all_comment_attempts_fail() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client.invocations.extend(
        [
            ReviewToolInvocation(
                tool_name="add_comment_to_pending_review",
                method=None,
                success=False,
                error="GitHub CLI command failed with exit code 422: gh api\nstdout:\n\nstderr:\nInvalid request",
            ),
            ReviewToolInvocation(
                tool_name="add_comment_to_pending_review",
                method=None,
                success=False,
                error="GitHub CLI command failed with exit code 422: gh api\nstdout:\n\nstderr:\nInvalid request",
            ),
        ]
    )

    assert client.posting_failure_reason() == (
        "failed to post inline review comments (2 attempt(s)): GitHub CLI command failed with exit code 422: gh api"
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
            error="gh: Unprocessable Entity (HTTP 422)",
        )
    )

    assert client.posting_failure_reason() == (
        "GitHub review tool pull_request_review_write(create) failed: gh: Unprocessable Entity (HTTP 422)"
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


def test_add_comment_rejects_out_of_range_line_at_stage_time() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    index = _stub_diff_index(
        ("ci/agentic-reviewer/src/odh_ci_agent/fetch_pr_source_snapshot.py", {1, 2, 3}),
    )

    with _patch_diff_index(client, index):
        try:
            client.add_comment_to_pending_review(
                path="ci/agentic-reviewer/src/odh_ci_agent/fetch_pr_source_snapshot.py",
                body="wrong file",
                subjectType="LINE",
                line=146,
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "Line 146 could not be resolved" in str(exc)

    assert client._draft_review_comments == []
    assert client.invocations[-1].success is False


def test_add_comment_deduplicates_identical_staged_payload() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    kwargs = {
        "path": "README.md",
        "body": "nit",
        "subjectType": "LINE",
        "line": 5,
    }

    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
        first = client.add_comment_to_pending_review(**kwargs)
        second = client.add_comment_to_pending_review(**kwargs)

    assert first == {"staged": True, "comment_count": 1}
    assert second == {"staged": True, "comment_count": 1, "deduplicated": True}
    assert len(client._draft_review_comments) == 1


def test_create_pending_review_revalidates_before_post() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._head_commit_id = "abc123"
    client._draft_review_comments.append(
        {
            "body": "nit",
            "path": "README.md",
            "line": 999,
            "side": "RIGHT",
        }
    )

    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
        try:
            client._create_pending_review("repos/owner/repo/pulls/12", "owner", "repo", 12, {})
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "Line 999 could not be resolved" in str(exc)


def test_review_outcome_empty_run() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)

    assert client.review_outcome() == {
        "add_comment_attempts": 0,
        "deduplicated_comment_attempts": 0,
        "inline_comments_posted": False,
        "inline_comments_staged": 0,
        "review_submitted": False,
    }


def test_review_outcome_staged_and_submitted() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._draft_review_comments.append(
        {
            "body": "nit",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        }
    )
    client.invocations.extend(
        [
            ReviewToolInvocation(tool_name="add_comment_to_pending_review", method=None, success=True),
            ReviewToolInvocation(tool_name="pull_request_review_write", method="submit_pending", success=True),
        ]
    )

    assert client.review_outcome() == {
        "add_comment_attempts": 1,
        "deduplicated_comment_attempts": 0,
        "inline_comments_posted": True,
        "inline_comments_staged": 1,
        "review_submitted": True,
    }


def test_review_outcome_staged_without_submit() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    client._draft_review_comments.append(
        {
            "body": "nit",
            "path": "README.md",
            "line": 5,
            "side": "RIGHT",
        }
    )
    client.invocations.append(
        ReviewToolInvocation(tool_name="add_comment_to_pending_review", method=None, success=True)
    )

    outcome = client.review_outcome()
    assert outcome["inline_comments_staged"] == 1
    assert outcome["review_submitted"] is False
    assert outcome["inline_comments_posted"] is False


def test_review_outcome_counts_deduplicated_attempts() -> None:
    client = GitHubReviewClient(repository="owner/repo", pull_number=12)
    kwargs = {
        "path": "README.md",
        "body": "nit",
        "subjectType": "LINE",
        "line": 5,
    }

    with _patch_diff_index(client, _stub_diff_index(("README.md", {5}))):
        client.add_comment_to_pending_review(**kwargs)
        client.add_comment_to_pending_review(**kwargs)

    outcome = client.review_outcome()
    assert outcome["add_comment_attempts"] == 2
    assert outcome["deduplicated_comment_attempts"] == 1
    assert outcome["inline_comments_staged"] == 1
