from __future__ import annotations

import json
from pathlib import Path

from scripts.cve.cve_groups import (
    CVEGroup,
    group_issues,
    notebooks_prodsec_jql,
    notebooks_rhoaieng_jql,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "classify"


def _load_fixture(key: str) -> dict:
    with open(FIXTURE_DIR / f"{key}.json", encoding="utf-8") as handle:
        return json.load(handle)


def test_notebooks_prodsec_jql_includes_rhai_and_rhoaieng() -> None:
    jql = notebooks_prodsec_jql()
    assert "project in (RHOAIENG, RHAI)" in jql
    assert 'component = "Notebooks Images"' in jql
    assert "labels = SecurityTracking" in jql
    assert notebooks_rhoaieng_jql() == jql


def test_group_issues_merges_rhoaieng_and_rhai_by_cve_branch() -> None:
    rhoaieng = _load_fixture("RHOAIENG-91786")
    rhai = _load_fixture("RHAI-3507")
    groups = group_issues([rhoaieng, rhai])
    group = groups["CVE-2026-78676", "rhoai-3.5"]
    assert group.rhoaieng_keys == [rhoaieng["key"]]
    assert group.rhai_keys == [rhai["key"]]
    assert group.source_keys == [rhoaieng["key"], rhai["key"]]
    assert group.anchor_key == rhoaieng["key"]
    assert group.ticket_count == 2


def test_cve_group_anchor_prefers_rhai_when_no_rhoaieng() -> None:
    rhai = _load_fixture("RHAI-3507")
    group = CVEGroup(
        cve_id="CVE-2026-78676",
        branch="rhoai-3.5",
        rhai_keys=[rhai["key"]],
    )
    assert group.anchor_key == rhai["key"]
    assert group.source_keys == [rhai["key"]]
