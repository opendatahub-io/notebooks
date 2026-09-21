"""Unit tests for CVE tracker labels and Team field helpers."""

from __future__ import annotations

from scripts.cve import create_cve_trackers as cct
from scripts.cve.create_cve_trackers import CveTrackerConfig


def test_build_tracker_labels() -> None:
    assert cct.build_tracker_labels("CVE-2026-28498") == [
        "CVE",
        "CVE-2026-28498",
        "security",
    ]


def test_build_tracker_team_extra_fields_default() -> None:
    fields = cct.build_tracker_team_extra_fields()
    assert fields == {cct.RHAIENG_TEAM_CUSTOM_FIELD: cct.RHAIENG_TEAM_OPTION_ID_DEFAULT}


def test_build_tracker_team_extra_fields_override() -> None:
    config = CveTrackerConfig(team_option_id="override-option-id")
    fields = cct.build_tracker_team_extra_fields(config)
    assert fields[cct.RHAIENG_TEAM_CUSTOM_FIELD] == "override-option-id"
