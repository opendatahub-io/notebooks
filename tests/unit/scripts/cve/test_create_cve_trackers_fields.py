"""Unit tests for CVE tracker labels and Team field helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
