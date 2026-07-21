"""Unit tests for JiraClient.create_issue extra_fields and constructor."""

from __future__ import annotations

from scripts.cve.jira_client import JiraClient

# ── Constructor ────────────────────────────────────────────────────────


def test_jira_client_direct_constructor() -> None:
    client = JiraClient("https://jira.example.com", {"Authorization": "Bearer tok"})
    assert client.base_url == "https://jira.example.com"
    assert client.headers["Authorization"] == "Bearer tok"
    assert client.headers["Content-Type"] == "application/json"


def test_jira_client_trailing_slash_stripped() -> None:
    client = JiraClient("https://jira.example.com/")
    assert client.base_url == "https://jira.example.com"


def test_jira_client_no_auth_headers() -> None:
    client = JiraClient("https://jira.example.com")
    assert "Authorization" not in client.headers


# ── create_issue extra_fields ──────────────────────────────────────────


def _capturing_client() -> tuple[JiraClient, dict]:
    client = JiraClient("https://jira.example", {})
    captured: dict = {}

    def fake_request(method: str, endpoint: str, params=None, data=None):
        if data:
            captured.update(data)
        return {"key": "RHAIENG-1"}

    client._request = fake_request
    return client, captured


def test_create_issue_merges_extra_fields() -> None:
    client, captured = _capturing_client()

    client.create_issue(
        "RHAIENG",
        "summary text",
        "Bug",
        labels=["CVE", "CVE-2026-1", "security"],
        extra_fields={"customfield_10001": "team-opt-1-uuid"},
    )

    assert captured["fields"]["labels"] == ["CVE", "CVE-2026-1", "security"]
    assert captured["fields"]["customfield_10001"] == "team-opt-1-uuid"


def test_create_issue_extra_fields_do_not_override_protected_keys() -> None:
    client, captured = _capturing_client()

    client.create_issue(
        "RHAIENG",
        "real summary",
        "Bug",
        labels=["CVE"],
        extra_fields={
            "labels": ["hijack"],
            "summary": "evil",
            "customfield_10001": "keep-me-uuid",
        },
    )

    assert captured["fields"]["labels"] == ["CVE"]
    assert captured["fields"]["summary"] == "real summary"
    assert captured["fields"]["customfield_10001"] == "keep-me-uuid"
