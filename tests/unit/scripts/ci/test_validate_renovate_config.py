from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.ci import validate_renovate_config as validator

if TYPE_CHECKING:
    import pytest


def test_pattern_matches_branch_exact_and_negation() -> None:
    assert validator._pattern_matches_branch("main", "main") is True
    assert validator._pattern_matches_branch("!/^main$/", "main") is False
    assert validator._pattern_matches_branch("!/^main$/", "rhoai-3.4") is True
    assert validator._pattern_matches_branch("/^rhoai-3\\.4$/", "rhoai-3.4") is True


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
    assert validator.commit_message_prefix_for_branch(config, "main") is None
    assert validator.commit_message_prefix_for_branch(config, "rhoai-3.4") == "[rhoai-3.4]"


def test_validate_config_reports_missing_prefix_rule() -> None:
    config = {"enabledManagers": list(validator.REQUIRED_ENABLED_MANAGERS), "packageRules": []}
    errors = validator.validate_config(config)
    assert any("Prefix PR titles" in message for message in errors)


def test_validate_config_rejects_shadow_renovate_json(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    shadow = tmp_path / "renovate.json"
    shadow.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(validator, "SHADOW_CONFIG", shadow)
    monkeypatch.setattr(validator, "ROOT", tmp_path)

    config = {
        "enabledManagers": list(validator.REQUIRED_ENABLED_MANAGERS),
        "packageRules": [
            {
                "description": validator.PREFIX_RULE_DESCRIPTION,
                "matchBaseBranches": validator.EXPECTED_PREFIX_MATCH_BASE,
                "commitMessagePrefix": validator.EXPECTED_COMMIT_MESSAGE_PREFIX,
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
    errors = validator.validate_config(config)
    assert any("must not exist" in message for message in errors)
