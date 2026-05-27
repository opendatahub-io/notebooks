from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.cve import create_cve_trackers as cct

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_extract_cve_id_from_label_and_summary() -> None:
    assert cct.extract_cve_id("CVE-2026-8643") == "CVE-2026-8643"
    assert cct.extract_cve_id("EMBARGOED CVE-2026-8643 foo") == "CVE-2026-8643"
    assert cct.extract_cve_id("no cve here") is None


def test_extract_version() -> None:
    summary = "EMBARGOED CVE-2026-8643 rhoai/odh-workbench: flaw [rhoai-2.25]"
    assert cct.extract_version(summary) == "rhoai-2.25"
    assert cct.extract_version("no version suffix") is None


def test_extract_description_strips_embargo_and_component() -> None:
    summary = "EMBARGOED CVE-2026-8643 rhoai/odh-workbench-jupyter-trustyai: Path traversal flaw [rhoai-2.25]"
    desc = cct.extract_description(summary, "CVE-2026-8643")
    assert desc == "Path traversal flaw"
    assert "EMBARGOED" not in desc


def test_child_is_embargoed_security_level() -> None:
    fields = {"security": {"name": cct.EMBARGOED_SECURITY_LEVEL}, "summary": "CVE-2026-8643 foo"}
    assert cct.child_is_embargoed(fields) is True


def test_child_is_embargoed_summary_prefix() -> None:
    fields = {"security": {"name": "Red Hat Employee"}, "summary": "EMBARGOED CVE-2026-8643 foo"}
    assert cct.child_is_embargoed(fields) is True


def test_child_is_not_embargoed() -> None:
    fields = {"security": {"name": "Red Hat Employee"}, "summary": "CVE-2026-8643 foo"}
    assert cct.child_is_embargoed(fields) is False


def test_extract_contributor_account_ids() -> None:
    fields = {
        cct.RHAIENG_CONTRIBUTORS_FIELD: [
            {"accountId": "557058:abc", "displayName": "Jiri Danek"},
            {"accountId": "606b693110a0a9006fd7ca32", "displayName": "Jay Koehler"},
        ]
    }
    assert cct.extract_contributor_account_ids(fields) == {
        "557058:abc",
        "606b693110a0a9006fd7ca32",
    }


def test_contributors_field_value_sorted() -> None:
    value = cct.contributors_field_value({"b-id", "a-id"})
    assert value == [{"accountId": "a-id"}, {"accountId": "b-id"}]


def test_build_tracker_summary_embargoed() -> None:
    info = cct.CVEInfo(
        cve_id="CVE-2026-8643",
        version="rhoai-2.25",
        description="Path traversal flaw",
        is_embargoed=True,
    )
    summary = cct.build_tracker_summary(info)
    assert summary.startswith("EMBARGOED CVE-2026-8643")
    assert summary.endswith("[rhoai-2.25]")


def test_build_tracker_summary_not_embargoed() -> None:
    info = cct.CVEInfo(
        cve_id="CVE-2026-8643",
        version="rhoai-2.25",
        description="Path traversal flaw",
        is_embargoed=False,
    )
    summary = cct.build_tracker_summary(info)
    assert not summary.startswith("EMBARGOED")
    assert summary.startswith("CVE-2026-8643")


def test_get_blocking_issues() -> None:
    issue = {
        "fields": {
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "inwardIssue": {"key": "RHAIENG-5306"},
                },
                {
                    "type": {"name": "Relates"},
                    "inwardIssue": {"key": "RHAIENG-9999"},
                },
            ]
        }
    }
    assert cct.get_blocking_issues(issue) == ["RHAIENG-5306"]


def test_parse_extra_contributor_ids(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_RHAIENG_EXTRA_CONTRIBUTORS", " id-one , id-two ")
    assert cct.parse_extra_contributor_ids() == {"id-one", "id-two"}
    monkeypatch.delenv("JIRA_RHAIENG_EXTRA_CONTRIBUTORS", raising=False)
    assert cct.parse_extra_contributor_ids() == set()


def test_find_orphan_cves_groups_embargo_and_contributors() -> None:
    class FakeClient:
        def search_issues(self, jql: str, fields: str, max_results: int = 500) -> list[dict]:
            return [
                {
                    "key": "RHOAIENG-64025",
                    "fields": {
                        "summary": ("EMBARGOED CVE-2026-8643 rhoai/odh-trustyai: flaw [rhoai-2.25]"),
                        "labels": ["SecurityTracking", "CVE-2026-8643"],
                        "security": {"name": cct.EMBARGOED_SECURITY_LEVEL},
                        cct.RHAIENG_CONTRIBUTORS_FIELD: [
                            {"accountId": "user-a"},
                        ],
                        "issuelinks": [],
                    },
                },
            ]

    result = cct.find_orphan_cves(FakeClient(), max_results=10)
    assert len(result.orphans) == 1
    info = next(iter(result.orphans.values()))
    assert info.is_embargoed is True
    assert info.contributor_account_ids == {"user-a"}
    assert info.cve_id == "CVE-2026-8643"
    assert info.version == "rhoai-2.25"
