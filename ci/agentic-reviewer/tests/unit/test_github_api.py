from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from odh_ci_agent import github_api


def test_split_repository() -> None:
    assert github_api.split_repository("owner/repo") == ("owner", "repo")


def test_split_repository_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="owner/repo format"):
        github_api.split_repository("not-a-repo")


def test_query_path_encodes_query_string() -> None:
    path = github_api._query_path("repos/foo/bar/issues", {"page": 2, "per_page": 50, "q": "hello world"})

    assert path.startswith("repos/foo/bar/issues?")
    assert "page=2" in path
    assert "per_page=50" in path
    assert "hello+world" in path


def test_gh_api_pages_rejects_non_positive_per_page() -> None:
    with pytest.raises(ValueError, match="per_page must be a positive integer"):
        github_api.gh_api_pages("repos/foo/bar/issues", item_key="items", per_page=0)


def test_gh_api_json_returns_none_on_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch(
        "odh_ci_agent.github_api.run_command",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ):
        result = github_api.gh_api_json("repos/owner/repo/pulls/1/reviews/1", method="DELETE")

    assert result is None


def test_parse_positive_issue_number_accepts_canonical_values() -> None:
    assert github_api.parse_positive_issue_number("3806") == 3806
    assert github_api.parse_positive_issue_number(" 42 ") == 42


@pytest.mark.parametrize("raw", ["0", "01", "1e3", "1.0", "", "abc"])
def test_parse_positive_issue_number_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError, match="Invalid"):
        github_api.parse_positive_issue_number(raw, label="pull request number")


def test_authenticated_user_login_returns_login(monkeypatch: pytest.MonkeyPatch) -> None:
    github_api.authenticated_user_login.cache_clear()
    monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)
    monkeypatch.delenv("REVIEW_AUTHOR_LOGIN", raising=False)
    try:
        with patch(
            "odh_ci_agent.github_api.gh_api_json",
            return_value={"login": "github-actions[bot]"},
        ) as mock_gh_api_json:
            assert github_api.authenticated_user_login() == "github-actions[bot]"
            assert github_api.authenticated_user_login() == "github-actions[bot]"
            mock_gh_api_json.assert_called_once_with("user")
    finally:
        github_api.authenticated_user_login.cache_clear()


def test_authenticated_user_login_uses_github_app_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    github_api.authenticated_user_login.cache_clear()
    monkeypatch.delenv("REVIEW_AUTHOR_LOGIN", raising=False)
    monkeypatch.setenv("GITHUB_APP_SLUG", "odh-antigravity")
    try:
        with patch("odh_ci_agent.github_api.gh_api_json") as mock_gh_api_json:
            assert github_api.authenticated_user_login() == "odh-antigravity[bot]"
            mock_gh_api_json.assert_not_called()
    finally:
        github_api.authenticated_user_login.cache_clear()
        monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)


def test_authenticated_user_login_falls_back_when_user_endpoint_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    github_api.authenticated_user_login.cache_clear()
    monkeypatch.delenv("REVIEW_AUTHOR_LOGIN", raising=False)
    monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)
    forbidden = github_api.GitHubCommandError(
        ("gh", "api", "user"),
        1,
        '{"message":"Resource not accessible by integration","status":"403"}',
        "gh: Resource not accessible by integration (HTTP 403)\n",
    )
    try:
        with patch("odh_ci_agent.github_api.gh_api_json", side_effect=forbidden):
            assert github_api.authenticated_user_login() == "github-actions[bot]"
    finally:
        github_api.authenticated_user_login.cache_clear()


def test_authenticated_user_login_reraises_non_forbidden_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    github_api.authenticated_user_login.cache_clear()
    monkeypatch.delenv("REVIEW_AUTHOR_LOGIN", raising=False)
    monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)
    server_error = github_api.GitHubCommandError(
        ("gh", "api", "user"),
        1,
        '{"message":"Internal Server Error","status":"500"}',
        "gh: Internal Server Error (HTTP 500)\n",
    )
    try:
        with patch("odh_ci_agent.github_api.gh_api_json", side_effect=server_error):
            with pytest.raises(github_api.GitHubCommandError) as exc_info:
                github_api.authenticated_user_login()
            assert exc_info.value is server_error
    finally:
        github_api.authenticated_user_login.cache_clear()


def test_authenticated_user_login_prefers_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    github_api.authenticated_user_login.cache_clear()
    monkeypatch.setenv("REVIEW_AUTHOR_LOGIN", "custom-bot[bot]")
    monkeypatch.setenv("GITHUB_APP_SLUG", "ignored-app")
    try:
        with patch("odh_ci_agent.github_api.gh_api_json") as mock_gh_api_json:
            assert github_api.authenticated_user_login() == "custom-bot[bot]"
            mock_gh_api_json.assert_not_called()
    finally:
        github_api.authenticated_user_login.cache_clear()
        monkeypatch.delenv("REVIEW_AUTHOR_LOGIN", raising=False)
        monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)


@pytest.mark.parametrize("user_response", [{"login": 12345}, {"login": ""}, {"login": None}, {}])
def test_authenticated_user_login_rejects_malformed_login(
    monkeypatch: pytest.MonkeyPatch,
    user_response: object,
) -> None:
    github_api.authenticated_user_login.cache_clear()
    monkeypatch.delenv("GITHUB_APP_SLUG", raising=False)
    monkeypatch.delenv("REVIEW_AUTHOR_LOGIN", raising=False)
    with patch("odh_ci_agent.github_api.gh_api_json", return_value=user_response):
        with pytest.raises(SystemExit, match="Expected GitHub user response to include login"):
            github_api.authenticated_user_login()
