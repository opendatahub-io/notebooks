from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.cve.classify_ticket import classify_ticket

if TYPE_CHECKING:
    from pytest import Subtests

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "classify"


def _load_fixture(key: str) -> dict:
    with open(FIXTURE_DIR / f"{key}.json", encoding="utf-8") as handle:
        return json.load(handle)


def test_python_rhaieng_parent_autofix() -> None:
    result = classify_ticket(_load_fixture("RHAIENG-6341"))
    assert result.package_type == "python"
    assert result.ticket_role == "rhaieng_parent"
    assert result.action == "autofix"
    assert result.verdict is None
    assert result.package == "pillow"
    assert result.branch == "rhoai-3.4"
    assert "CVE-2026-59205" in result.cve_ids


def test_rhoaieng_child_skipped() -> None:
    result = classify_ticket(_load_fixture("RHOAIENG-77242"))
    assert result.ticket_role == "rhoaieng_child"
    assert result.action == "skip"
    assert result.verdict == "not_fixable"


def test_go_rhaieng_parent_not_fixable() -> None:
    result = classify_ticket(_load_fixture("RHAIENG-6695"))
    assert result.package_type == "go"
    assert result.ticket_role == "rhaieng_parent"
    assert result.action == "skip"
    assert result.verdict == "not_fixable"
    assert "github.com/docker/docker" in (result.package or "")


def test_rpm_rhaieng_parent_rpm_check() -> None:
    result = classify_ticket(_load_fixture("RHAIENG-6699"))
    assert result.package_type == "rpm"
    assert result.ticket_role == "rhaieng_parent"
    assert result.action == "rpm_check"
    assert result.package == "nginx"
    assert result.branch == "rhoai-3.5"


def test_java_rhaieng_parent_not_fixable() -> None:
    result = classify_ticket(_load_fixture("RHAIENG-6792"))
    assert result.package_type == "java"
    assert result.ticket_role == "rhaieng_parent"
    assert result.action == "skip"
    assert result.verdict == "not_fixable"


def test_npm_rhaieng_parent_not_fixable() -> None:
    result = classify_ticket(_load_fixture("RHAIENG-6810"))
    assert result.package_type == "npm"
    assert result.ticket_role == "rhaieng_parent"
    assert result.action == "skip"
    assert result.verdict == "not_fixable"
    assert result.package == "code-server"


def test_openssl_not_classified_as_python() -> None:
    issue = {
        "key": "RHAIENG-9999",
        "fields": {
            "project": {"key": "RHAIENG"},
            "summary": "CVE-2026-1234 openssl [rhoai-3.4]",
            "description": "Tracker for openssl CVE.\n\n**Blocked Issues (1):** RHOAIENG-99999",
            "labels": ["CVE", "CVE-2026-1234", "security"],
            "issuetype": {"name": "Bug"},
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "outwardIssue": {"key": "RHOAIENG-99999"},
                }
            ],
        },
    }
    result = classify_ticket(issue)
    assert result.package_type == "unknown"
    assert result.action == "needs_info"
    assert result.verdict == "needs_info"


def test_autofix_without_branch_needs_info() -> None:
    issue = {
        "key": "RHAIENG-9998",
        "fields": {
            "project": {"key": "RHAIENG"},
            "summary": "CVE-2026-9999 Requests: example vulnerability",
            "description": "Tracker without branch suffix.\n\n**Blocked Issues (1):** RHOAIENG-99998",
            "labels": ["CVE", "security"],
            "issuetype": {"name": "Bug"},
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "outwardIssue": {"key": "RHOAIENG-99998"},
                }
            ],
        },
    }
    result = classify_ticket(issue)
    assert result.package_type == "python"
    assert result.action == "needs_info"
    assert result.verdict == "needs_info"
    assert result.branch is None


def test_epic_scenarios(subtests: Subtests) -> None:
    """Cover all six epic test-plan scenarios via fixtures."""
    scenarios = {
        "python rhoai-3.4 parent": ("RHAIENG-6341", "autofix"),
        "rhoaieng per-image child": ("RHOAIENG-77242", "skip"),
        "nginx rpm rhsa path": ("RHAIENG-6699", "rpm_check"),
        "docker go not_fixable": ("RHAIENG-6695", "skip"),
        "jackson java not_fixable": ("RHAIENG-6792", "skip"),
        "code-server npm not_fixable": ("RHAIENG-6810", "skip"),
    }
    for name, (key, expected_action) in scenarios.items():
        with subtests.test(msg=name):
            result = classify_ticket(_load_fixture(key))
            assert result.action == expected_action
