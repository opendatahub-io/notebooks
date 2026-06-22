from __future__ import annotations

import pytest

from scripts.ci import github_api


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
