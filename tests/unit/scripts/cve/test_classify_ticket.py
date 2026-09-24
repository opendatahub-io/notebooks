from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.cve.classify_ticket import classify_ticket, main
from scripts.cve.jira_auth import JiraAuthError, JiraConnectionConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "classify"


def _load_fixture(key: str) -> dict:
    with open(FIXTURE_DIR / f"{key}.json", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize(
    ("fixture_key", "package_type", "ticket_role", "action", "verdict", "package", "branch"),
    [
        ("RHAIENG-6341", "python", "rhaieng_parent", "autofix", None, "pillow", "rhoai-3.4"),
        ("RHOAIENG-77242", "python", "rhoaieng_source", "autofix", None, "pillow", "rhoai-3.4"),
        ("RHOAIENG-91786", "python", "rhoaieng_source", "autofix", None, "gitpython", "rhoai-3.5"),
        ("RHAIENG-6695", "go", "rhaieng_parent", "skip", "not_fixable", "github.com/docker/docker", "rhoai-3.5"),
        ("RHAIENG-6699", "rpm", "rhaieng_parent", "rpm_check", None, "nginx", "rhoai-3.5"),
        (
            "RHAIENG-6792",
            "java",
            "rhaieng_parent",
            "skip",
            "not_fixable",
            "com.fasterxml.jackson.core:jackson-databind",
            "rhoai-3.5",
        ),
        ("RHAIENG-6810", "npm", "rhaieng_parent", "skip", "not_fixable", "code-server", "rhoai-3.4"),
    ],
)
def test_fixture_classifications(
    fixture_key: str,
    package_type: str,
    ticket_role: str,
    action: str,
    verdict: str | None,
    package: str | None,
    branch: str | None,
) -> None:
    result = classify_ticket(_load_fixture(fixture_key))
    assert result.package_type == package_type
    assert result.ticket_role == ticket_role
    assert result.action == action
    assert result.verdict == verdict
    assert result.package == package
    assert result.branch == branch


def test_python_parent_includes_cve_id() -> None:
    result = classify_ticket(_load_fixture("RHAIENG-6341"))
    assert "CVE-2026-59205" in result.cve_ids


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


def test_main_loads_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["RHAIENG-6341", "--fixture-dir", str(FIXTURE_DIR), "--pretty"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "autofix"
    assert payload["dry_run"] is False


def test_main_rejects_fixture_path_outside_dir() -> None:
    with pytest.raises(SystemExit):
        main(["../RHAIENG-6341", "--fixture-dir", str(FIXTURE_DIR)])


def test_main_offline_fixture_does_not_build_jira_config(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_config(_environ: object) -> JiraConnectionConfig:
        raise AssertionError("offline fixture should not build Jira configuration")

    monkeypatch.setattr(JiraConnectionConfig, "from_env", fail_config)

    assert main(["RHAIENG-6341", "--fixture-dir", str(FIXTURE_DIR)]) == 0


def test_main_reports_auth_error_for_remote_issue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_config(_environ: object) -> JiraConnectionConfig:
        raise JiraAuthError("invalid Jira configuration")

    monkeypatch.setattr(JiraConnectionConfig, "from_env", fail_config)

    assert main(["RHAIENG-1", "--fixture-dir", str(tmp_path)]) == 1
    assert "invalid Jira configuration" in capsys.readouterr().err
