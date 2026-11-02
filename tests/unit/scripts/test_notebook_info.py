from __future__ import annotations

import pytest

from scripts.notebook_info.config import RELEASES
from scripts.notebook_info.org_pulse import OrgPulseClient, org_pulse_client_from_env
from scripts.notebook_info.report import build_report, format_grades, format_grades_summary, jira_link, org_pulse_link


def test_jira_link_uses_filter_id_when_available() -> None:
    config = RELEASES["2.25"]
    assert jira_link(config, "https://jira.example") == ("https://jira.example/issues?filter=115488")


def test_jira_link_falls_back_to_jql_when_no_filter_id() -> None:
    config = RELEASES["3.3"]
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


def test_build_report_uses_all_sources() -> None:
    counts = dict.fromkeys(RELEASES, 0)
    freezes = dict.fromkeys(RELEASES)
    grades = {release: {} for release in RELEASES}
    counts["2.25"] = 11
    grades["2.25"] = {"A": 18}
    report = build_report(
        counts,
        freezes,
        grades,
        "https://jira.example",
        "https://org-pulse.example",
    )
    assert "Notebook Status —" in report
    assert "2.25" in report
    assert "A:18" in report
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
    freezes = client.code_freezes(RELEASES)
    assert freezes["3.3"] == "2026-01-16"
    assert freezes["3.4"] == "2026-07-31"


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
