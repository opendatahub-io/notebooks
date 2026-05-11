"""Unit tests for scripts/cve/jira_client.py — direct constructor and field logic."""

from __future__ import annotations

from typing import ClassVar

from scripts.cve.jira_client import _CREATE_ISSUE_PROTECTED_FIELD_KEYS, JiraClient


class TestJiraClientConstruction:
    def test_direct_constructor(self) -> None:
        client = JiraClient("https://jira.example.com", {"Authorization": "Bearer tok"})
        assert client.base_url == "https://jira.example.com"
        assert client.headers["Authorization"] == "Bearer tok"
        assert client.headers["Content-Type"] == "application/json"

    def test_trailing_slash_stripped(self) -> None:
        client = JiraClient("https://jira.example.com/")
        assert client.base_url == "https://jira.example.com"

    def test_no_auth_headers(self) -> None:
        client = JiraClient("https://jira.example.com")
        assert "Authorization" not in client.headers


class TestProtectedFieldKeys:
    _REQUIRED_KEYS: ClassVar[set[str]] = {
        "project",
        "summary",
        "issuetype",
        "description",
        "labels",
        "components",
        "security",
    }

    def test_contains_required_keys(self) -> None:
        assert self._REQUIRED_KEYS.issubset(_CREATE_ISSUE_PROTECTED_FIELD_KEYS)

    def test_no_unexpected_additions(self) -> None:
        extra = _CREATE_ISSUE_PROTECTED_FIELD_KEYS - self._REQUIRED_KEYS
        assert extra == set(), f"unexpected protected keys added: {extra}"

    def test_custom_field_not_protected(self) -> None:
        assert "customfield_10001" not in _CREATE_ISSUE_PROTECTED_FIELD_KEYS
