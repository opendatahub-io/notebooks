from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.ci.validate_renovate_config import (
    EXPECTED_COMMIT_MESSAGE_PREFIX,
    EXPECTED_PREFIX_MATCH_BASE,
    MINTMAKER_POLICIES,
    MintMakerRepoPolicy,
    PREFIX_RULE_DESCRIPTION,
    REQUIRED_ENABLED_MANAGERS,
)


def prefix_rule() -> dict[str, Any]:
    return {
        "description": PREFIX_RULE_DESCRIPTION,
        "matchBaseBranches": EXPECTED_PREFIX_MATCH_BASE,
        "commitMessagePrefix": EXPECTED_COMMIT_MESSAGE_PREFIX,
    }


def mintmaker_gate_rules(policy: MintMakerRepoPolicy) -> list[dict[str, Any]]:
    return [
        {"matchRepositories": [policy.repository], "enabled": False},
        {
            "matchRepositories": [policy.repository],
            "matchBaseBranches": sorted(policy.enabled_branches),
            "enabled": True,
        },
    ]


def github_actions_group_rule() -> dict[str, Any]:
    return {
        "matchManagers": ["github-actions"],
        "groupName": "github-actions",
        "pinDigests": True,
    }


def minimal_valid_config(*extra_rules: dict[str, Any]) -> dict[str, Any]:
    package_rules: list[dict[str, Any]] = [prefix_rule()]
    for policy in MINTMAKER_POLICIES:
        package_rules.extend(mintmaker_gate_rules(policy))
    package_rules.append(github_actions_group_rule())
    package_rules.extend(extra_rules)
    return {
        "enabledManagers": list(REQUIRED_ENABLED_MANAGERS),
        "packageRules": package_rules,
    }


def with_package_rules_removed(
    config: dict[str, Any],
    predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    package_rules = [
        rule
        for rule in config["packageRules"]
        if not (isinstance(rule, dict) and predicate(rule))
    ]
    return {**config, "packageRules": package_rules}


def policy_by_label(label: str) -> MintMakerRepoPolicy:
    for policy in MINTMAKER_POLICIES:
        if policy.label == label:
            return policy
    msg = f"unknown MintMaker policy label: {label!r}"
    raise KeyError(msg)


def remove_mintmaker_disable(config: dict[str, Any], policy: MintMakerRepoPolicy) -> dict[str, Any]:
    return with_package_rules_removed(
        config,
        lambda rule: rule.get("matchRepositories") == [policy.repository] and rule.get("enabled") is False,
    )


def remove_mintmaker_enable(config: dict[str, Any], policy: MintMakerRepoPolicy) -> dict[str, Any]:
    return with_package_rules_removed(
        config,
        lambda rule: (
            rule.get("matchRepositories") == [policy.repository]
            and rule.get("enabled") is True
            and "matchBaseBranches" in rule
        ),
    )


def mintmaker_enable_with_branches(
    config: dict[str, Any],
    policy: MintMakerRepoPolicy,
    branches: list[str],
) -> dict[str, Any]:
    updated_rules: list[dict[str, Any]] = []
    for rule in config["packageRules"]:
        if not isinstance(rule, dict):
            updated_rules.append(rule)
            continue
        if (
            rule.get("matchRepositories") == [policy.repository]
            and rule.get("enabled") is True
            and "matchBaseBranches" in rule
        ):
            updated_rules.append({**rule, "matchBaseBranches": branches})
            continue
        updated_rules.append(rule)
    return {**config, "packageRules": updated_rules}
