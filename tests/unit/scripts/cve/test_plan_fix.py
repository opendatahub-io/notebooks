from __future__ import annotations

import json
from pathlib import Path

from scripts.cve.cve_groups import CVEGroup
from scripts.cve.plan_fix import build_fix_plan, parse_constraints_text, parse_fixed_version

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "classify"


def _load_fixture(key: str) -> dict:
    with open(FIXTURE_DIR / f"{key}.json", encoding="utf-8") as handle:
        return json.load(handle)


def test_parse_fixed_version_before() -> None:
    assert parse_fixed_version("GitPython before 3.1.59 Remote Code Execution") == "3.1.59"


def test_parse_constraints_text() -> None:
    text = "# comment\npillow>=12.2.0\nurllib3>=2.7.0\n"
    assert parse_constraints_text(text) == {"pillow": "12.2.0", "urllib3": "2.7.0"}


def test_build_fix_plan_for_rhoaieng_gitpython() -> None:
    issue = _load_fixture("RHOAIENG-91786")
    group = CVEGroup(
        cve_id="CVE-2026-78676",
        branch="rhoai-3.5",
        rhoaieng_keys=["RHOAIENG-91786"],
        summaries={"RHOAIENG-91786": issue["fields"]["summary"]},
    )
    plan = build_fix_plan(group, anchor_issue=issue, dry_run=True)
    assert plan.classification.action == "autofix"
    assert plan.package == "gitpython"
    assert plan.floor_version == "3.1.59"
    assert plan.constraint_line == "gitpython>=3.1.59"
    assert plan.pr_branch == "fix/cve-CVE-2026-78676-rhoai-3.5"
