from __future__ import annotations

from scripts.ci import validate_renovate_config as validator


def test_pattern_matches_branch_exact_and_negation() -> None:
    assert validator._pattern_matches_branch("main", "main") is True, "Expected exact branch match for 'main'"
    assert validator._pattern_matches_branch("!/^main$/", "main") is False, (
        "Expected negated main pattern to reject 'main'"
    )
    assert validator._pattern_matches_branch("!/^main$/", "rhoai-3.4") is True, (
        "Expected negated main pattern to accept 'rhoai-3.4'"
    )
    assert validator._pattern_matches_branch("/^rhoai-3\\.4$/", "rhoai-3.4") is True, (
        "Expected anchored rhoai-3.4 pattern to match 'rhoai-3.4'"
    )


def test_commit_message_prefix_for_branch_merged_rules() -> None:
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
        "Expected disabled main rule to remove prefix"
    )
    assert validator.commit_message_prefix_for_branch(config, "rhoai-3.4") == "[rhoai-3.4]", (
        "Expected release branch prefix from merged packageRules"
    )


def test_renovate_enabled_for_odh_main_only() -> None:
    config = {
        "packageRules": [
            {"matchRepositories": [validator.ODH_REPO], "enabled": False},
            {
                "matchRepositories": [validator.ODH_REPO],
                "matchBaseBranches": sorted(validator.ODH_ENABLED_BRANCHES),
                "enabled": True,
            },
        ]
    }
    assert validator.renovate_enabled_for(config, validator.ODH_REPO, "main") is True, (
        "Expected MintMaker enabled on ODH main"
    )
    assert validator.renovate_enabled_for(config, validator.ODH_REPO, "stable") is False, (
        "Expected MintMaker disabled on ODH stable"
    )


def test_validate_config_reports_missing_prefix_rule() -> None:
    config = {"enabledManagers": list(validator.REQUIRED_ENABLED_MANAGERS), "packageRules": []}
    errors = validator.validate_config(config)
    assert any("Prefix PR titles" in message for message in errors), (
        f"Expected missing prefix rule error, got: {errors}"
    )


def test_validate_config_rejects_shadow_renovate_json(tmp_path) -> None:
    shadow = tmp_path / "renovate.json"
    shadow.write_text("{}", encoding="utf-8")

    config = {
        "enabledManagers": list(validator.REQUIRED_ENABLED_MANAGERS),
        "packageRules": [
            {
                "description": validator.PREFIX_RULE_DESCRIPTION,
                "matchBaseBranches": validator.EXPECTED_PREFIX_MATCH_BASE,
                "commitMessagePrefix": validator.EXPECTED_COMMIT_MESSAGE_PREFIX,
            },
            {"matchRepositories": [validator.ODH_REPO], "enabled": False},
            {
                "matchRepositories": [validator.ODH_REPO],
                "matchBaseBranches": sorted(validator.ODH_ENABLED_BRANCHES),
                "enabled": True,
            },
            {"matchRepositories": [validator.RHDS_REPO], "enabled": False},
            {
                "matchRepositories": [validator.RHDS_REPO],
                "matchBaseBranches": sorted(validator.RHDS_ENABLED_BRANCHES),
                "enabled": True,
            },
            {
                "matchManagers": ["github-actions"],
                "groupName": "github-actions",
                "pinDigests": True,
            },
        ],
    }
    errors = validator.validate_config(config, config_dir=tmp_path)
    assert any("must not exist" in message for message in errors), (
        f"Expected shadow renovate.json validation error, got: {errors}"
    )
