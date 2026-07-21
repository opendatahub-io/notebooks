"""Unit tests for CVE tracker labels and Team field helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from scripts.cve import create_cve_trackers as cct

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_build_tracker_labels() -> None:
    assert cct.build_tracker_labels("CVE-2026-28498") == [
        "CVE",
        "CVE-2026-28498",
        "security",
    ]


def test_build_tracker_team_extra_fields_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_RHAIENG_TEAM_OPTION_ID", raising=False)
    fields = cct.build_tracker_team_extra_fields()
    assert fields == {cct.RHAIENG_TEAM_CUSTOM_FIELD: cct.RHAIENG_TEAM_OPTION_ID_DEFAULT}


def test_build_tracker_team_extra_fields_env_override(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_RHAIENG_TEAM_OPTION_ID", "override-option-id")
    fields = cct.build_tracker_team_extra_fields()
    assert fields[cct.RHAIENG_TEAM_CUSTOM_FIELD] == "override-option-id"


def test_create_tracker_issue_passes_labels_and_team(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_RHAIENG_TEAM_OPTION_ID", raising=False)
    monkeypatch.delenv("JIRA_RHAIENG_EXTRA_CONTRIBUTORS", raising=False)
    monkeypatch.delenv("JIRA_RUNNER_ACCOUNT_ID", raising=False)

    client = MagicMock()
    client.create_issue.return_value = {"key": "RHAIENG-99"}
    client.get_current_user.return_value = {"accountId": "runner-id-123"}

    info = cct.CVEInfo(cve_id="CVE-2026-99999", version="rhoai-3.3", description="Authlib test")
    info.issues = [{"key": "RHOAIENG-1", "summary": "child", "has_parent": False}]

    key = cct.create_tracker_issue(
        client,
        info,
        jira_url="https://redhat.atlassian.net",
        dry_run=False,
    )

    assert key == "RHAIENG-99"
    client.create_issue.assert_called_once()
    kwargs = client.create_issue.call_args.kwargs
    assert kwargs["labels"] == ["CVE", "CVE-2026-99999", "security"]
    assert kwargs["extra_fields"][cct.RHAIENG_TEAM_CUSTOM_FIELD] == cct.RHAIENG_TEAM_OPTION_ID_DEFAULT
