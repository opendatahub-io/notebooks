from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from inline_snapshot import snapshot

from scripts.cve import create_cve_trackers as cct

if TYPE_CHECKING:
    from pytest import MonkeyPatch, Subtests

    from scripts.cve.jira_client import JiraClient


def _render_adf_inline(node: dict) -> str:
    text = node.get("text", "")
    marks = node.get("marks", [])
    for mark in marks:
        if mark["type"] == "strong":
            text = f"**{text}**"
        elif mark["type"] == "link":
            href = mark.get("attrs", {}).get("href", "")
            text = f"[{text}]({href})"
    return text


def adf_to_text(doc: dict) -> str:
    parts: list[str] = []
    for node in doc.get("content", []):
        if node["type"] == "paragraph":
            line = "".join(_render_adf_inline(child) for child in node.get("content", []))
            parts.append(line)
        elif node["type"] == "codeBlock":
            code = "".join(child.get("text", "") for child in node.get("content", []))
            parts.append(f"`{code}`")
    return "\n".join(parts)


def test_extract_cve_id_from_label_and_summary(subtests: Subtests) -> None:
    cases = [
        ("CVE-2026-8643", "CVE-2026-8643"),
        ("EMBARGOED CVE-2026-8643 foo", "CVE-2026-8643"),
        ("no cve here", None),
    ]
    for raw, expected in cases:
        with subtests.test(msg=f"extract_cve_id({raw!r})"):
            assert cct.extract_cve_id(raw) == expected


def test_extract_version(subtests: Subtests) -> None:
    cases = [
        ("EMBARGOED CVE-2026-8643 rhoai/odh-workbench: flaw [rhoai-2.25]", "rhoai-2.25"),
        ("no version suffix", None),
    ]
    for summary, expected in cases:
        with subtests.test(msg=f"extract_version({summary!r})"):
            assert cct.extract_version(summary) == expected


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

    result = cct.find_orphan_cves(cast("JiraClient", FakeClient()), max_results=10)
    assert len(result.orphans) == 1
    info = next(iter(result.orphans.values()))
    assert info.is_embargoed is True
    assert info.contributor_account_ids == {"user-a"}
    assert info.cve_id == "CVE-2026-8643"
    assert info.version == "rhoai-2.25"


def test_build_description_with_version() -> None:
    info = cct.CVEInfo(
        cve_id="CVE-2026-8643",
        version="rhoai-2.25",
        description="Path traversal flaw",
        issues=[{"key": "RHOAIENG-64025"}, {"key": "RHOAIENG-64026"}],
    )
    assert adf_to_text(cct.build_description(info)) == snapshot("""\
Tracker for CVE-2026-8643 - Path traversal flaw affecting Notebooks Images components.
Fix should be applied to: [https://github.com/red-hat-data-services/notebooks](https://github.com/red-hat-data-services/notebooks) (branch: rhoai-2.25)
**Blocked Issues (2): **RHOAIENG-64025, RHOAIENG-64026
**JQL Query to View All Blocked Issues: **
[View all 2 blocked issues](https://redhat.atlassian.net/issues/?jql=key%20in%20%28RHOAIENG-64025%2C%20RHOAIENG-64026%29%20ORDER%20BY%20key%20ASC)\
""")


def test_build_description_no_version() -> None:
    info = cct.CVEInfo(
        cve_id="CVE-2026-8643",
        version="",
        description="Path traversal flaw",
    )
    assert adf_to_text(cct.build_description(info)) == snapshot("""\
Tracker for CVE-2026-8643 - Path traversal flaw affecting Notebooks Images components.
Fix should be applied to: [https://github.com/red-hat-data-services/notebooks](https://github.com/red-hat-data-services/notebooks) (on the respective release branch)\
""")


def test_create_tracker_issue_api_payload(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def create_issue(self, **kwargs: Any) -> dict:
            captured.update(kwargs)
            return {"key": "RHAIENG-9999"}

        def get_current_user(self) -> dict:
            return {"accountId": "runner-id-123"}

    monkeypatch.delenv("JIRA_RHAIENG_EXTRA_CONTRIBUTORS", raising=False)
    monkeypatch.delenv("JIRA_RUNNER_ACCOUNT_ID", raising=False)

    info = cct.CVEInfo(
        cve_id="CVE-2026-8643",
        version="rhoai-3.3",
        description="Path traversal flaw",
        issues=[{"key": "RHOAIENG-64025"}],
        is_embargoed=False,
        contributor_account_ids={"child-contrib-id"},
    )

    result = cct.create_tracker_issue(cast("JiraClient", FakeClient()), info)
    assert result == "RHAIENG-9999"

    assert adf_to_text(captured.pop("description")) == snapshot("""\
Tracker for CVE-2026-8643 - Path traversal flaw affecting Notebooks Images components.
Fix should be applied to: [https://github.com/red-hat-data-services/notebooks](https://github.com/red-hat-data-services/notebooks) (branch: rhoai-3.3)
**Blocked Issues (1): **RHOAIENG-64025
**JQL Query to View All Blocked Issues: **
[View all 1 blocked issues](https://redhat.atlassian.net/issues/?jql=key%20in%20%28RHOAIENG-64025%29%20ORDER%20BY%20key%20ASC)\
""")

    assert captured == snapshot(
        {
            "project_key": "RHAIENG",
            "summary": "CVE-2026-8643 Path traversal flaw [rhoai-3.3]",
            "issue_type": "Bug",
            "labels": ["CVE", "CVE-2026-8643", "security"],
            "components": ["Notebooks"],
            "security_level": "Red Hat Employee",
            "extra_fields": {
                "customfield_10001": "ec74d716-af36-4b3c-950f-f79213d08f71-62",
                "customfield_10855": [{"name": "rhoai-3.3"}],
                "customfield_10466": [{"accountId": "child-contrib-id"}, {"accountId": "runner-id-123"}],
            },
        }
    )


def test_create_tracker_issue_no_version_omits_target_version(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def create_issue(self, **kwargs: Any) -> dict:
            captured.update(kwargs)
            return {"key": "RHAIENG-8888"}

        def get_current_user(self) -> dict:
            return {"accountId": "runner-id-123"}

    monkeypatch.delenv("JIRA_RHAIENG_EXTRA_CONTRIBUTORS", raising=False)
    monkeypatch.delenv("JIRA_RUNNER_ACCOUNT_ID", raising=False)

    info = cct.CVEInfo(
        cve_id="CVE-2026-9999",
        version="",
        description="Some flaw",
    )

    cct.create_tracker_issue(cast("JiraClient", FakeClient()), info)
    assert cct.RHAIENG_TARGET_VERSION_FIELD not in captured.get("extra_fields", {})
