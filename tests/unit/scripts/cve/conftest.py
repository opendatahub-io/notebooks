"""Shared test fixtures for the CVE scripts unit tests.

Clears all Jira-related environment variables before every test so that a
developer's local environment cannot leak into assertions. Each test then only
needs to ``monkeypatch.setenv`` the variables it explicitly requires.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_jira_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Jira env vars that would otherwise leak from a developer shell."""
    for var in (
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "JIRA_TOKEN",
        "JIRA_OAUTH_CLIENT_SECRET",
        "JIRA_RHAIENG_TEAM_OPTION_ID",
        "JIRA_RHAIENG_EXTRA_CONTRIBUTORS",
        "JIRA_RUNNER_ACCOUNT_ID",
    ):
        monkeypatch.delenv(var, raising=False)
