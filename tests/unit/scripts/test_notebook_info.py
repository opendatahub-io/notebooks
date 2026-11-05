from __future__ import annotations

from datetime import datetime

import pytest

from scripts.notebook_info.config import RELEASES, ReleaseConfig
from scripts.notebook_info.lifecycle import SupportWindow, support_windows_from_payload
from scripts.notebook_info.org_pulse import OrgPulseClient, org_pulse_client_from_env
from scripts.notebook_info.report import (
    EASTERN,
    build_report,
    format_date,
    format_grades,
    format_grades_summary,
    format_support,
    jira_link,
    org_pulse_link,
    resolve_slack_channel,
)


def test_jira_link_uses_filter_id_when_available() -> None:
    config = RELEASES["2.25"]
    assert jira_link(config, "https://jira.example") == ("https://jira.example/issues?filter=115488")


def test_jira_link_falls_back_to_jql_when_no_filter_id() -> None:
    config = RELEASES["3.7"]
    assert jira_link(config, "https://jira.example").startswith("https://jira.example/issues/?jql=")


def test_org_pulse_link_is_derived_from_base_url() -> None:
    assert org_pulse_link("https://org-pulse.example") == (
        "https://org-pulse.example/#/releases/reports?report=container-health-index"
    )


def test_format_grades_orders_and_omits_empty_grades() -> None:
    assert format_grades({"Unknown": 1, "B": 2, "A": 3}) == "A:3, B:2, Unknown:1"


def test_format_grades_summary_uses_release_order() -> None:
    grades = {"3.4": {"A": 1}, "3.5": {"Unknown": 2}}
    assert format_grades_summary(grades) == "3.4: A:1\n3.5: Unknown:2"


def test_tracked_releases_drop_eol_3_3_and_include_3_7() -> None:
    assert list(RELEASES) == ["2.25", "3.4", "3.5", "3.6", "3.7"]


def test_format_date_omits_the_current_year() -> None:
    year = datetime.now(EASTERN).year
    assert format_date(f"{year}-07-31") == "Jul/31"
    assert format_date(f"{year + 1}-07-31") == f"Jul/31/{year + 1}"
    assert format_date(None) == "—"


def test_format_support_uses_phase_ends() -> None:
    year = datetime.now(EASTERN).year
    window = SupportWindow(f"{year}-05-25", f"{year + 1}-04-26")
    assert format_support(window) == f"Apr/26/{year + 1}"
    assert format_support(SupportWindow(f"{year}-11-16", None)) == "Nov/16"
    assert format_support(None) == "—"


def test_support_windows_from_payload_keeps_unpublished_releases_empty() -> None:
    payload = {
        "data": [
            {
                "name": "Red Hat OpenShift AI Self-Managed",
                "versions": [
                    {
                        "name": "3.5",
                        "phases": [
                            {
                                "name": "Full support",
                                "end_date": "2027-03-29T00:00:00.000Z",
                                "end_date_format": "date",
                            },
                            {
                                "name": "Extended update support",
                                "end_date": "2028-02-28T00:00:00.000Z",
                                "end_date_format": "date",
                            },
                        ],
                    },
                    {
                        "name": "3.4",
                        "phases": [
                            {
                                "name": "Full support",
                                "end_date": "2026-11-16T00:00:00.000Z",
                                "end_date_format": "date",
                            },
                            {
                                "name": "Extended update support",
                                "end_date": "N/A",
                                "end_date_format": "string",
                            },
                        ],
                    },
                ],
            }
        ]
    }
    windows = support_windows_from_payload(payload, {"3.4", "3.5", "3.7"})
    assert windows["3.5"] == SupportWindow("2027-03-29", "2028-02-28")
    assert windows["3.4"] == SupportWindow("2026-11-16", None)
    assert windows["3.7"] is None


def test_slack_channel_prefers_argument_and_environment() -> None:
    assert resolve_slack_channel("CARGUMENT", "CENVIRONMENT") == "CARGUMENT"
    assert resolve_slack_channel(None, "CENVIRONMENT") == "CENVIRONMENT"
    assert resolve_slack_channel(None, None) == "C096ZR053RQ"


def test_build_report_uses_all_sources() -> None:
    counts = dict.fromkeys(RELEASES, 0)
    freezes = dict.fromkeys(RELEASES)
    grades = {release: {} for release in RELEASES}
    support = dict.fromkeys(RELEASES)
    counts["2.25"] = 11
    grades["2.25"] = {"A": 18}
    support["2.25"] = SupportWindow("2026-05-25", "2027-04-26")
    report = build_report(
        counts,
        freezes,
        grades,
        support,
        "https://jira.example",
        "https://org-pulse.example",
    )
    assert "Notebook Status —" in report
    assert "- Release - Open - CF - Grade - EOL" in report
    assert "2.25" in report
    assert "3.7" in report
    assert "3.3" not in report
    assert "A:18" in report
    assert format_date("2027-04-26") in report
    assert "Org Pulse Container Health Index" in report


def test_org_pulse_code_freezes_use_api_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OrgPulseClient("https://org-pulse.example", "token")
    registry = {
        "releases": [
            {
                "id": "rhoai-3.4",
                "milestones": {"codeFreeze": "2026-07-31"},
            }
        ]
    }
    monkeypatch.setattr(OrgPulseClient, "release_registry", lambda self: registry)
    fallback = ReleaseConfig(version="9.9", jql="project = RHAI", jira_filter_id=None, code_freeze="2026-01-16")
    freezes = client.code_freezes({"3.4": RELEASES["3.4"], "3.7": RELEASES["3.7"], "9.9": fallback})
    assert freezes["9.9"] == "2026-01-16"
    assert freezes["3.4"] == "2026-07-31"
    assert freezes["3.7"] is None


def test_org_pulse_chi_grades_count_only_notebook_images(monkeypatch: pytest.MonkeyPatch) -> None:
    hierarchy = {
        "environments": {
            "latest": {
                "versions": [
                    {
                        "id": "rhoai-3.4",
                        "components": [
                            {
                                "name": "Notebooks Images",
                                "images": [
                                    {"grade": "A"},
                                    {"grade": "A"},
                                    {"grade": "B"},
                                    {"grade": None},
                                ],
                            },
                            {
                                "name": "Another Component",
                                "images": [{"grade": "F"}],
                            },
                        ],
                    }
                ]
            }
        }
    }
    client = OrgPulseClient("https://org-pulse.example", "token")
    monkeypatch.setattr(OrgPulseClient, "chi_hierarchy", lambda self: hierarchy)
    grades = client.chi_grades({"3.4": RELEASES["3.4"]})
    assert grades == {"3.4": {"A": 2, "B": 1, "Unknown": 1}}


def test_report_requires_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORG_PULSE_API_BASE", raising=False)
    monkeypatch.delenv("ORG_PULSE_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="ORG_PULSE_API_BASE"):
        org_pulse_client_from_env()
