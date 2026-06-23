from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from scripts.ci import validate_renovate_config as validator
from tests.unit.scripts.ci import renovate_config_testdata as testdata

POLICY_ENABLED_CASES = [
    pytest.param(policy, branch, True, id=f"{policy.label}-{branch}-enabled")
    for policy in validator.MINTMAKER_POLICIES
    for branch in sorted(policy.enabled_branches)
]

POLICY_DISABLED_CASES = [
    pytest.param(policy, branch, False, id=f"{policy.label}-{branch}-disabled")
    for policy in validator.MINTMAKER_POLICIES
    for branch in sorted(policy.disabled_branches)
]

MATCH_BASE_BRANCH_CASES = [
    pytest.param({"matchBaseBranches": ["main"]}, "main", True, id="exact-main"),
    pytest.param({"matchBaseBranches": ["!/^main$/"]}, "main", False, id="negated-main"),
    pytest.param({"matchBaseBranches": ["!/^main$/"]}, "rhoai-3.4", True, id="negated-release"),
    pytest.param({"matchBaseBranches": ["/^rhoai-3\\.4$/"]}, "rhoai-3.4", True, id="anchored-release"),
]

PREFIX_CASES = [
    pytest.param("main", None, id="main-unprefixed"),
    *[
        pytest.param(branch, f"[{branch}]", id=f"{branch}-prefixed")
        for branch in sorted(validator.RHDS_ENABLED_BRANCHES)
    ],
]


def _odh_policy() -> validator.MintMakerRepoPolicy:
    return testdata.policy_by_label("ODH")


def _rhds_policy() -> validator.MintMakerRepoPolicy:
    return testdata.policy_by_label("RHDS")


def test_minimal_valid_config_passes_validation() -> None:
    errors = validator.validate_config(testdata.minimal_valid_config())
    assert errors == [], f"Expected minimal synthetic config to pass validation, got: {errors}"


@pytest.mark.parametrize(("policy", "branch", "expected_enabled"), POLICY_ENABLED_CASES)
def test_renovate_enabled_for_matches_policy_enabled_branches(
    policy: validator.MintMakerRepoPolicy,
    branch: str,
    expected_enabled: bool,
) -> None:
    config = {"packageRules": testdata.mintmaker_gate_rules(policy)}
    assert validator.renovate_enabled_for(config, policy.repository, branch) is expected_enabled, (
        f"Expected MintMaker enabled={expected_enabled} for {policy.repository!r} @ {branch!r}"
    )


@pytest.mark.parametrize(("policy", "branch", "expected_enabled"), POLICY_DISABLED_CASES)
def test_renovate_enabled_for_matches_policy_disabled_branches(
    policy: validator.MintMakerRepoPolicy,
    branch: str,
    expected_enabled: bool,
) -> None:
    config = {"packageRules": testdata.mintmaker_gate_rules(policy)}
    assert validator.renovate_enabled_for(config, policy.repository, branch) is expected_enabled, (
        f"Expected MintMaker enabled={expected_enabled} for {policy.repository!r} @ {branch!r}"
    )


@pytest.mark.parametrize(("rule", "branch", "expected"), MATCH_BASE_BRANCH_CASES)
def test_match_base_branches(rule: dict[str, Any], branch: str, expected: bool) -> None:
    assert validator.match_base_branches(rule, branch) is expected, (
        f"Expected match_base_branches({rule!r}, {branch!r}) == {expected}"
    )


@pytest.mark.parametrize(("branch", "expected_prefix"), PREFIX_CASES)
def test_commit_message_prefix_for_branch(branch: str, expected_prefix: str | None) -> None:
    config = testdata.minimal_valid_config()
    assert validator.commit_message_prefix_for_branch(config, branch) == expected_prefix, (
        f"Expected commitMessagePrefix for {branch!r} to be {expected_prefix!r}"
    )


def test_commit_message_prefix_skips_disabled_main_rule() -> None:
    config = {
        "packageRules": [
            {
                "matchBaseBranches": ["!/^main$/"],
                "commitMessagePrefix": "[{{{baseBranch}}}]",
            },
            {
                "matchBaseBranches": ["main"],
                "enabled": False,
            },
        ]
    }
    assert validator.commit_message_prefix_for_branch(config, "main") is None, (
        "Expected disabled main rule to suppress prefix on main"
    )


@pytest.mark.parametrize(
    ("mutator", "expected_errors"),
    [
        pytest.param(
            lambda config: testdata.with_package_rules_removed(
                config,
                lambda rule: rule.get("description", "").startswith(validator.PREFIX_RULE_DESCRIPTION),
            ),
            [
                f"missing packageRule: {validator.PREFIX_RULE_DESCRIPTION!r}",
                "commitMessagePrefix for 'rhoai-2.25' must be '[rhoai-2.25]', got None",
                "commitMessagePrefix for 'rhoai-3.3' must be '[rhoai-3.3]', got None",
                "commitMessagePrefix for 'rhoai-3.4' must be '[rhoai-3.4]', got None",
            ],
            id="missing-prefix-rule",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_disable(config, _odh_policy()),
            [
                "missing ODH MintMaker disable rule for 'opendatahub-io/notebooks'",
                "MintMaker must be disabled for 'opendatahub-io/notebooks' @ 'candidate'",
                "MintMaker must be disabled for 'opendatahub-io/notebooks' @ 'konflux-poc-1'",
                "MintMaker must be disabled for 'opendatahub-io/notebooks' @ 'stable'",
            ],
            id="missing-odh-disable",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_enable(config, _odh_policy()),
            [
                "missing ODH MintMaker enable rule for 'opendatahub-io/notebooks'",
                "MintMaker must stay enabled for 'opendatahub-io/notebooks' @ main",
            ],
            id="missing-odh-enable",
        ),
        pytest.param(
            lambda config: testdata.mintmaker_enable_with_branches(config, _odh_policy(), ["stable"]),
            [
                "ODH enable rule matchBaseBranches must be ['main'], got ['stable']",
                "MintMaker must stay enabled for 'opendatahub-io/notebooks' @ main",
                "MintMaker must be disabled for 'opendatahub-io/notebooks' @ 'stable'",
            ],
            id="odh-enable-wrong-branches",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_disable(config, _rhds_policy()),
            [
                "missing RHDS MintMaker disable rule for 'red-hat-data-services/notebooks'",
                "MintMaker must be disabled for 'red-hat-data-services/notebooks' @ 'main'",
            ],
            id="missing-rhds-disable",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_enable(config, _rhds_policy()),
            [
                "missing RHDS MintMaker enable rule for 'red-hat-data-services/notebooks'",
                "MintMaker must stay enabled for 'red-hat-data-services/notebooks' @ rhoai-2.25",
                "MintMaker must stay enabled for 'red-hat-data-services/notebooks' @ rhoai-3.3",
                "MintMaker must stay enabled for 'red-hat-data-services/notebooks' @ rhoai-3.4",
            ],
            id="missing-rhds-enable",
        ),
        pytest.param(
            lambda config: testdata.mintmaker_enable_with_branches(
                config,
                _rhds_policy(),
                ["rhoai-2.25"],
            ),
            [
                "RHDS enable rule matchBaseBranches must be "
                "['rhoai-2.25', 'rhoai-3.3', 'rhoai-3.4'], got ['rhoai-2.25']",
                "MintMaker must stay enabled for 'red-hat-data-services/notebooks' @ rhoai-3.3",
                "MintMaker must stay enabled for 'red-hat-data-services/notebooks' @ rhoai-3.4",
            ],
            id="rhds-enable-wrong-branches",
        ),
        pytest.param(
            lambda config: testdata.with_package_rules_removed(
                config,
                lambda rule: rule.get("groupName") == "github-actions",
            ),
            ["missing github-actions group packageRule"],
            id="missing-github-actions-group",
        ),
        pytest.param(
            lambda config: {
                **config,
                "packageRules": [
                    *config["packageRules"],
                    {
                        "matchRepositories": [validator.ODH_REPO],
                        "matchBaseBranches": ["stable"],
                        "enabled": True,
                    },
                ],
            },
            ["MintMaker must be disabled for 'opendatahub-io/notebooks' @ 'stable'"],
            id="odh-stable-enabled-by-extra-rule",
        ),
    ],
)
def test_validate_config_reports_expected_errors(
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
    expected_errors: list[str],
) -> None:
    config = mutator(testdata.minimal_valid_config())
    errors = validator.validate_config(config)
    assert errors == expected_errors, f"Expected validation errors {expected_errors!r}, got {errors!r}"


def test_validate_config_rejects_shadow_renovate_json(tmp_path) -> None:
    shadow = tmp_path / "renovate.json"
    shadow.write_text("{}", encoding="utf-8")

    errors = validator.validate_config(testdata.minimal_valid_config(), config_dir=tmp_path)
    assert len(errors) == 1, f"Expected one shadow-file error, got: {errors}"
    assert "must not exist (shadows renovate.json5)" in errors[0], (
        f"Expected shadow renovate.json validation error, got: {errors}"
    )
