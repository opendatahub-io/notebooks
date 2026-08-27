from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def _clean_jira_env(monkeypatch: MonkeyPatch) -> None:
    """Clear Jira env vars so tests are not affected by a local environment.

    Tests only need to ``setenv`` the vars they explicitly require.
    """
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
