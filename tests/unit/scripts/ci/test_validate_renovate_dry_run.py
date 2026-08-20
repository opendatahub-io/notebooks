from __future__ import annotations

import json
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

TEST_ENV = {"RENOVATE_TOKEN": "test-token"}


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
    assert "expected at least one PR title" in errors[0], f"Unexpected validation error message: {errors[0]}"


def test_validate_scenario_titles_empty_falls_back_to_combined_config() -> None:
    scenario = dry_run.SCENARIOS[1]
    records = dry_run.parse_json_log_lines(
        """
{"msg":"Combined config","config":{"packageRules":[{"description":"Prefix PR titles with branch name for non-main branches","matchBaseBranches":["!/^main$/"],"commitMessagePrefix":"[{{{baseBranch}}}]"}]}}
"""
    )
    errors = dry_run.validate_scenario_titles(scenario, [], records=records)
    assert errors == [], f"Expected empty titles to pass via Combined config fallback, got: {errors}"


def test_validate_scenario_titles_empty_without_prefix_rule_fails() -> None:
    scenario = dry_run.SCENARIOS[1]
    records = dry_run.parse_json_log_lines('{"msg":"Combined config","config":{"packageRules":[]}}')
    errors = dry_run.validate_scenario_titles(scenario, [], records=records)
    assert len(errors) == 1, f"Expected exactly one validation error, got: {errors}"
    assert "missing the PR-title prefix packageRule" in errors[0], f"Unexpected error: {errors[0]}"


def _combined_config_record(rule: dict) -> str:
    return json.dumps({"msg": "Combined config", "config": {"packageRules": [rule]}})


def _separate_minor_patch_rule(**overrides: object) -> dict:
    rule = {
        "description": dry_run.SEPARATE_MINOR_PATCH_RULE_DESCRIPTION,
        "matchManagers": ["custom.regex"],
        "matchPackageNames": dry_run.SEPARATE_MINOR_PATCH_MATCH_PACKAGE_NAMES,
        "separateMinorPatch": True,
    }
    rule.update(overrides)
    return rule


def test_validate_separate_minor_patch_rule_passes() -> None:
    records = dry_run.parse_json_log_lines(_combined_config_record(_separate_minor_patch_rule()))
    errors = dry_run.validate_separate_minor_patch_rule(records)
    assert errors == [], f"Expected valid separateMinorPatch rule to pass, got: {errors}"


def test_validate_separate_minor_patch_rule_missing() -> None:
    records = dry_run.parse_json_log_lines('{"msg":"Combined config","config":{"packageRules":[]}}')
    errors = dry_run.validate_separate_minor_patch_rule(records)
    assert len(errors) == 1, f"Expected exactly one validation error, got: {errors}"
    assert "missing the separateMinorPatch packageRule" in errors[0], f"Unexpected error: {errors[0]}"


def test_validate_separate_minor_patch_rule_disabled() -> None:
    records = dry_run.parse_json_log_lines(
        _combined_config_record(_separate_minor_patch_rule(separateMinorPatch=False))
    )
    errors = dry_run.validate_separate_minor_patch_rule(records)
    assert len(errors) == 1, f"Expected exactly one validation error, got: {errors}"
    assert "must set separateMinorPatch: true" in errors[0], f"Unexpected error: {errors[0]}"


def test_validate_separate_minor_patch_rule_missing_package_names() -> None:
    rule = _separate_minor_patch_rule()
    del rule["matchPackageNames"]
    records = dry_run.parse_json_log_lines(_combined_config_record(rule))
    errors = dry_run.validate_separate_minor_patch_rule(records)
    assert len(errors) == 1, f"Expected exactly one validation error, got: {errors}"
    assert "matchPackageNames must be" in errors[0], f"Unexpected error: {errors[0]}"


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


def test_build_dry_run_env_sets_scenario_fields() -> None:
    scenario = dry_run.SCENARIOS[0]
    env = dry_run.build_dry_run_env(scenario, TEST_ENV)
    assert env["RENOVATE_REPOSITORIES"] == "opendatahub-io/notebooks", (
        f"Expected repository from scenario, got {env['RENOVATE_REPOSITORIES']!r}"
    )
    assert env["RENOVATE_BASE_BRANCHES"] == "main", (
        f"Expected base branch from scenario, got {env['RENOVATE_BASE_BRANCHES']!r}"
    )
    assert env["LOG_FORMAT"] == "json", f"Expected JSON log format, got {env['LOG_FORMAT']!r}"
    assert env["LOG_LEVEL"] == "debug", f"Expected debug log level for prTitle extraction, got {env['LOG_LEVEL']!r}"


def test_validate_dry_runs_requires_renovate_token() -> None:
    errors = dry_run.validate_dry_runs(renovate_token="", base_env=TEST_ENV)
    assert errors == ["RENOVATE_TOKEN is not set"], f"Expected missing token error, got: {errors}"


def test_run_dry_run_timeout() -> None:
    scenario = dry_run.SCENARIOS[0]
    timeout_seconds = 123
    env = dry_run.build_dry_run_env(scenario, TEST_ENV)

    def fake_run(*_args, **kwargs):
        assert kwargs["timeout"] == timeout_seconds, (
            f"Expected timeout {timeout_seconds}, got {kwargs.get('timeout')!r}"
        )
        raise subprocess.TimeoutExpired(
            cmd=["renovate"],
            timeout=timeout_seconds,
            output='{"msg":"partial"}',
            stderr="",
        )

    with pytest.raises(RuntimeError, match="timed out after 123s"):
        dry_run.run_dry_run(scenario, env=env, timeout_seconds=timeout_seconds, runner=fake_run)
