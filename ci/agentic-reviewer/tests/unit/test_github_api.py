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
