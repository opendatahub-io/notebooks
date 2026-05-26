from __future__ import annotations

import subprocess

import pytest

from scripts.ci import validate_renovate_dry_run as dry_run

MAIN_FIXTURE = """
{"prTitle":"Update github-actions"}
{"prTitle":"Update Konflux references"}
{"warnings":[{"message":"You must configure baseBranchPatterns in order to use them inside matchBaseBranches."}]}
"""

RHOAI_FIXTURE = """
{"branchesInformation":[{"prTitle":"[rhoai-3.4] Update github-actions (major)"}]}
{"prTitle":"[rhoai-3.4] Update Konflux references"}
"""


def test_extract_pr_titles_from_fixture_logs() -> None:
    main_records = dry_run.parse_json_log_lines(MAIN_FIXTURE)
    rhoai_records = dry_run.parse_json_log_lines(RHOAI_FIXTURE)
    main_titles = dry_run.extract_pr_titles(main_records)
    assert main_titles == [
        "Update github-actions",
        "Update Konflux references",
    ], f"Expected unprefixed main PR titles, got: {main_titles}"
    rhoai_titles = dry_run.extract_pr_titles(rhoai_records)
    assert rhoai_titles == [
        "[rhoai-3.4] Update github-actions (major)",
        "[rhoai-3.4] Update Konflux references",
    ], f"Expected prefixed rhoai-3.4 PR titles, got: {rhoai_titles}"


def test_validate_scenario_titles_main_unprefixed() -> None:
    scenario = dry_run.SCENARIOS[0]
    titles = dry_run.extract_pr_titles(dry_run.parse_json_log_lines(MAIN_FIXTURE))
    errors = dry_run.validate_scenario_titles(scenario, titles)
    assert errors == [], f"Expected main scenario to pass with unprefixed titles, got: {errors}"


def test_validate_scenario_titles_rhoai_prefixed() -> None:
    scenario = dry_run.SCENARIOS[1]
    titles = dry_run.extract_pr_titles(dry_run.parse_json_log_lines(RHOAI_FIXTURE))
    errors = dry_run.validate_scenario_titles(scenario, titles)
    assert errors == [], f"Expected rhoai-3.4 scenario to pass with prefixed titles, got: {errors}"


def test_validate_scenario_titles_detects_missing_prefix() -> None:
    scenario = dry_run.SCENARIOS[1]
    errors = dry_run.validate_scenario_titles(scenario, ["Update github-actions"])
    assert len(errors) == 1, f"Expected exactly one validation error, got: {errors}"
    assert "expected at least one PR title" in errors[0], (
        f"Unexpected validation error message: {errors[0]}"
    )


def test_fatal_config_warnings_ignores_known_cosmetic() -> None:
    records = dry_run.parse_json_log_lines(MAIN_FIXTURE)
    warnings = dry_run.fatal_config_warnings(records)
    assert warnings == [], f"Expected known cosmetic warnings to be ignored, got: {warnings}"


def test_fatal_config_warnings_ignores_package_rules_prefix() -> None:
    records = dry_run.parse_json_log_lines(
        '{"warnings":[{"message":"packageRules[0]: You must configure baseBranchPatterns in order to use them inside matchBaseBranches."}]}'
    )
    warnings = dry_run.fatal_config_warnings(records)
    assert warnings == [], f"Expected packageRules-prefixed warning to be ignored, got: {warnings}"


def test_run_dry_run_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["renovate"],
            timeout=dry_run.DEFAULT_DRY_RUN_TIMEOUT_SECONDS,
            output='{"msg":"partial"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="timed out after 900s"):
        dry_run.run_dry_run(dry_run.SCENARIOS[0])
