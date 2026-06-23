from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from scripts.ci import validate_renovate_config as validator
from tests.unit.scripts.ci import renovate_config_testdata as testdata

if TYPE_CHECKING:
    from collections.abc import Callable


def _odh_policy() -> validator.MintMakerRepoPolicy:
    return testdata.policy_by_label("ODH")


def _rhds_policy() -> validator.MintMakerRepoPolicy:
    return testdata.policy_by_label("RHDS")


def test_minimal_valid_config_passes_validation() -> None:
    errors = validator.validate_config(testdata.minimal_valid_config())
    assert errors == [], f"Expected minimal synthetic config to pass validation, got: {errors}"


@pytest.mark.parametrize(
    ("mutator", "expected_errors"),
    [
        pytest.param(
            lambda config: testdata.with_package_rules_removed(
                config,
                lambda rule: rule.get("description", "").startswith(validator.PREFIX_RULE_DESCRIPTION),
            ),
            [f"missing packageRule: {validator.PREFIX_RULE_DESCRIPTION!r}"],
            id="missing-prefix-rule",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_disable(config, _odh_policy()),
            ["missing ODH MintMaker disable rule for 'opendatahub-io/notebooks'"],
            id="missing-odh-disable",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_enable(config, _odh_policy()),
            ["missing ODH MintMaker enable rule for 'opendatahub-io/notebooks'"],
            id="missing-odh-enable",
        ),
        pytest.param(
            lambda config: testdata.mintmaker_enable_with_branches(config, _odh_policy(), ["stable"]),
            ["ODH enable rule matchBaseBranches must be ['main'], got ['stable']"],
            id="odh-enable-wrong-branches",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_disable(config, _rhds_policy()),
            ["missing RHDS MintMaker disable rule for 'red-hat-data-services/notebooks'"],
            id="missing-rhds-disable",
        ),
        pytest.param(
            lambda config: testdata.remove_mintmaker_enable(config, _rhds_policy()),
            ["missing RHDS MintMaker enable rule for 'red-hat-data-services/notebooks'"],
            id="missing-rhds-enable",
        ),
        pytest.param(
            lambda config: testdata.mintmaker_enable_with_branches(
                config,
                _rhds_policy(),
                ["rhoai-2.25"],
            ),
            [
                (
                    "RHDS enable rule matchBaseBranches must be "
                    "['rhoai-2.25', 'rhoai-3.3', 'rhoai-3.4'], got ['rhoai-2.25']"
                ),
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
            lambda config: testdata.with_package_rules_removed(
                config,
                lambda rule: rule.get("description", "").startswith(validator.CENTOS_STREAM_RULE_DESCRIPTION),
            ),
            [f"missing CentOS Stream pin packageRule: {validator.CENTOS_STREAM_RULE_DESCRIPTION!r}"],
            id="missing-centos-stream-pin",
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
