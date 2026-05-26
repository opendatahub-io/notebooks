from __future__ import annotations

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
    assert dry_run.extract_pr_titles(main_records) == [
        "Update github-actions",
        "Update Konflux references",
    ]
    assert dry_run.extract_pr_titles(rhoai_records) == [
        "[rhoai-3.4] Update github-actions (major)",
        "[rhoai-3.4] Update Konflux references",
    ]


def test_validate_scenario_titles_main_unprefixed() -> None:
    scenario = dry_run.SCENARIOS[0]
    titles = dry_run.extract_pr_titles(dry_run.parse_json_log_lines(MAIN_FIXTURE))
    assert dry_run.validate_scenario_titles(scenario, titles) == []


def test_validate_scenario_titles_rhoai_prefixed() -> None:
    scenario = dry_run.SCENARIOS[1]
    titles = dry_run.extract_pr_titles(dry_run.parse_json_log_lines(RHOAI_FIXTURE))
    assert dry_run.validate_scenario_titles(scenario, titles) == []


def test_validate_scenario_titles_detects_missing_prefix() -> None:
    scenario = dry_run.SCENARIOS[1]
    errors = dry_run.validate_scenario_titles(scenario, ["Update github-actions"])
    assert len(errors) == 1
    assert "expected at least one PR title" in errors[0]


def test_fatal_config_warnings_ignores_known_cosmetic() -> None:
    records = dry_run.parse_json_log_lines(MAIN_FIXTURE)
    assert dry_run.fatal_config_warnings(records) == []
