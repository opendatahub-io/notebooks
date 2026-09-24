from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.cve.fix_cve import main

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "classify"


@pytest.mark.parametrize("constraints", ["", "gitpython>=3.1.59\n"])
@pytest.mark.parametrize("json_output", [False, True])
def test_fix_cve_dry_run_offline_rhoaieng(capsys, monkeypatch, constraints, json_output) -> None:
    monkeypatch.setattr("scripts.cve.fix_cve.JiraClient", SimpleNamespace(from_env=lambda: None))
    monkeypatch.setattr("scripts.cve.plan_fix.read_constraints_for_branch", lambda *a, **kw: constraints)
    monkeypatch.setattr("scripts.cve.plan_fix.find_open_pr", lambda *a, **kw: None)
    assert (
        main(
            [
                "RHOAIENG-91786",
                "--dry-run",
                "--fixture-dir",
                str(FIXTURE_DIR),
                *(["--json"] if json_output else []),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "CVE-2026-78676:rhoai-3.5" in output
    assert "gitpython>=3.1.59" in output
    if json_output:
        plan = json.loads(output)
        assert plan["dry_run"] is True
        assert plan["verdict"] == ("already_fixed" if constraints else None)
    else:
        assert "Dry-run only" in output
        if constraints:
            assert "already_fixed" in output
