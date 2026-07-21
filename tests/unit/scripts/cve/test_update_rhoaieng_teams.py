from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from scripts.cve import create_cve_trackers as cct

if TYPE_CHECKING:
    from pytest import CaptureFixture


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def expected_team_id() -> str:
    return cct.RHAIENG_TEAM_OPTION_ID_DEFAULT


def test_update_rhoaieng_teams_no_updates_needed(mock_client: MagicMock, expected_team_id: str) -> None:
    issues = [
        {
            "key": "RHOAIENG-1",
            "fields": {cct.RHAIENG_TEAM_CUSTOM_FIELD: {"id": expected_team_id, "value": "AAIET Notebooks"}},
        },
        {
            "key": "RHOAIENG-2",
            "fields": {cct.RHAIENG_TEAM_CUSTOM_FIELD: expected_team_id},
        },
    ]

    cct.update_rhoaieng_teams(mock_client, issues, dry_run=False)
    mock_client.update_issue.assert_not_called()


def test_update_rhoaieng_teams_updates_needed(mock_client: MagicMock, expected_team_id: str) -> None:
    issues = [
        {"key": "RHOAIENG-1", "fields": {}},
        {"key": "RHOAIENG-2", "fields": {cct.RHAIENG_TEAM_CUSTOM_FIELD: {"id": "wrong-id", "value": "Wrong Team"}}},
        {"key": "RHOAIENG-3", "fields": {cct.RHAIENG_TEAM_CUSTOM_FIELD: "wrong-string-id"}},
        {"key": "RHOAIENG-4", "fields": {cct.RHAIENG_TEAM_CUSTOM_FIELD: 12345}},
    ]

    cct.update_rhoaieng_teams(mock_client, issues, dry_run=False)
    assert mock_client.update_issue.call_count == 4

    expected_team_extra = cct.build_tracker_team_extra_fields()

    mock_client.update_issue.assert_any_call("RHOAIENG-1", expected_team_extra)
    mock_client.update_issue.assert_any_call("RHOAIENG-2", expected_team_extra)
    mock_client.update_issue.assert_any_call("RHOAIENG-3", expected_team_extra)
    mock_client.update_issue.assert_any_call("RHOAIENG-4", expected_team_extra)


def test_update_rhoaieng_teams_dry_run(mock_client: MagicMock, expected_team_id: str) -> None:
    issues = [{"key": "RHOAIENG-1", "fields": {}}]

    cct.update_rhoaieng_teams(mock_client, issues, dry_run=True)
    mock_client.update_issue.assert_not_called()


def test_update_rhoaieng_teams_handles_exception(
    mock_client: MagicMock,
    expected_team_id: str,
    capsys: CaptureFixture[str],
) -> None:
    issues = [{"key": "RHOAIENG-1", "fields": {}}]

    mock_client.update_issue.side_effect = Exception("Jira went boom")

    cct.update_rhoaieng_teams(mock_client, issues, dry_run=False)

    mock_client.update_issue.assert_called_once()

    captured = capsys.readouterr()
    assert "ERROR setting Team on RHOAIENG-1: Jira went boom" in captured.out
    assert "Updated Team field on" not in captured.out
