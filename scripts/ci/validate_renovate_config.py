#!/usr/bin/env python3
"""Validate .github/renovate.json5 syntax and repo-specific semantic invariants."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyjson5

SCRIPTS_CI = Path(__file__).resolve().parent
ROOT = SCRIPTS_CI.parent.parent
DEFAULT_CONFIG = ROOT / ".github" / "renovate.json5"

REQUIRED_ENABLED_MANAGERS = frozenset({"tekton", "dockerfile", "custom.regex", "github-actions"})
ODH_REPO = "opendatahub-io/notebooks"
RHDS_REPO = "red-hat-data-services/notebooks"
RHDS_ENABLED_BRANCHES = frozenset({"rhoai-2.25", "rhoai-3.3", "rhoai-3.4"})
PREFIX_RULE_DESCRIPTION = "Prefix PR titles with branch name for non-main branches"
EXPECTED_PREFIX_MATCH_BASE = ["!/^main$/"]
EXPECTED_COMMIT_MESSAGE_PREFIX = "[{{{baseBranch}}}]"


@dataclass(frozen=True)
class MintMakerRepoPolicy:
    label: str
    repository: str
    enabled_branches: frozenset[str]
    disabled_branches: frozenset[str]


MINTMAKER_POLICIES = (
    MintMakerRepoPolicy(
        label="ODH",
        repository=ODH_REPO,
        enabled_branches=frozenset({"main"}),
        disabled_branches=frozenset({"stable", "candidate", "konflux-poc-1"}),
    ),
    MintMakerRepoPolicy(
        label="RHDS",
        repository=RHDS_REPO,
        enabled_branches=RHDS_ENABLED_BRANCHES,
        disabled_branches=frozenset({"main"}),
    ),
)

ODH_ENABLED_BRANCHES = MINTMAKER_POLICIES[0].enabled_branches


def load_config(path: Path) -> dict[str, Any]:
    data = pyjson5.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{path}: expected top-level object, got {type(data).__name__}"
        raise ValueError(msg)
    return data


def _pattern_matches_branch(pattern: str, base_branch: str) -> bool:
    if pattern.startswith("!/") and pattern.endswith("/"):
        inner = pattern[2:-1]
        return re.fullmatch(inner, base_branch) is None
    if pattern.startswith("/") and pattern.endswith("/"):
        inner = pattern[1:-1]
        return re.fullmatch(inner, base_branch) is not None
    return pattern == base_branch


def match_base_branches(rule: dict[str, Any], base_branch: str) -> bool:
    patterns = rule.get("matchBaseBranches")
    if not patterns:
        return True
    if not isinstance(patterns, list):
        return True
    return any(_pattern_matches_branch(str(item), base_branch) for item in patterns)


def rule_applies(rule: dict[str, Any], base_branch: str) -> bool:
    if "enabled" in rule and rule["enabled"] is False:
        return False
    return match_base_branches(rule, base_branch)


def find_repo_rule(
    package_rules: list[Any],
    repository: str,
    *,
    enabled: bool,
    require_match_base_branches: bool | None = None,
) -> dict[str, Any] | None:
    for rule in package_rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("matchRepositories") != [repository]:
            continue
        if rule.get("enabled") is not enabled:
            continue
        has_match_base_branches = "matchBaseBranches" in rule
        if require_match_base_branches is True and not has_match_base_branches:
            continue
        if require_match_base_branches is False and has_match_base_branches:
            continue
        return rule
    return None


def renovate_enabled_for(config: dict[str, Any], repository: str, base_branch: str) -> bool:
    enabled = True
    for rule in config.get("packageRules", []):
        if not isinstance(rule, dict):
            continue
        repos = rule.get("matchRepositories")
        if not isinstance(repos, list) or repository not in repos:
            continue
        if "enabled" not in rule:
            continue
        if not match_base_branches(rule, base_branch):
            continue
        enabled = bool(rule["enabled"])
    return enabled


def validate_mintmaker_policy(
    config: dict[str, Any],
    package_rules: list[Any],
    policy: MintMakerRepoPolicy,
) -> list[str]:
    errors: list[str] = []

    disable_rule = find_repo_rule(
        package_rules,
        policy.repository,
        enabled=False,
        require_match_base_branches=False,
    )
    if disable_rule is None:
        errors.append(f"missing {policy.label} MintMaker disable rule for {policy.repository!r}")

    enable_rule = find_repo_rule(
        package_rules,
        policy.repository,
        enabled=True,
        require_match_base_branches=True,
    )
    if enable_rule is None:
        errors.append(f"missing {policy.label} MintMaker enable rule for {policy.repository!r}")
    elif set(enable_rule.get("matchBaseBranches", [])) != policy.enabled_branches:
        errors.append(
            f"{policy.label} enable rule matchBaseBranches must be "
            f"{sorted(policy.enabled_branches)!r}, got {enable_rule.get('matchBaseBranches')!r}"
        )

    for branch in sorted(policy.enabled_branches):
        if not renovate_enabled_for(config, policy.repository, branch):
            errors.append(f"MintMaker must stay enabled for {policy.repository!r} @ {branch}")

    for branch in sorted(policy.disabled_branches):
        if renovate_enabled_for(config, policy.repository, branch):
            errors.append(f"MintMaker must be disabled for {policy.repository!r} @ {branch!r}")

    return errors


def commit_message_prefix_for_branch(config: dict[str, Any], base_branch: str) -> str | None:
    prefix: str | None = None
    for rule in config.get("packageRules", []):
        if not isinstance(rule, dict):
            continue
        if not rule_applies(rule, base_branch):
            continue
        if "commitMessagePrefix" in rule:
            raw = rule["commitMessagePrefix"]
            if not isinstance(raw, str):
                continue
            prefix = raw.replace("{{{baseBranch}}}", base_branch)
    return prefix


def validate_config(config: dict[str, Any], *, config_dir: Path = ROOT / ".github") -> list[str]:
    errors: list[str] = []

    shadow_config = config_dir / "renovate.json"
    if shadow_config.is_file():
        rel = shadow_config.relative_to(ROOT) if shadow_config.is_relative_to(ROOT) else shadow_config
        errors.append(f"{rel} must not exist (shadows renovate.json5)")

    for forbidden in ("baseBranchPatterns", "baseBranches"):
        if forbidden in config:
            errors.append(f"top-level {forbidden!r} must not be set (breaks MintMaker per-branch config)")

    managers = config.get("enabledManagers")
    if not isinstance(managers, list):
        errors.append("enabledManagers must be a list")
    else:
        missing = REQUIRED_ENABLED_MANAGERS - set(managers)
        if missing:
            errors.append(f"enabledManagers missing: {sorted(missing)}")

    package_rules = config.get("packageRules")
    if not isinstance(package_rules, list):
        errors.append("packageRules must be a list")
        return errors

    prefix_rule = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict) and rule.get("description", "").startswith(PREFIX_RULE_DESCRIPTION)
        ),
        None,
    )
    if prefix_rule is None:
        errors.append(f"missing packageRule: {PREFIX_RULE_DESCRIPTION!r}")
    else:
        if package_rules.index(prefix_rule) != 0:
            errors.append("prefix packageRule must be first in packageRules")
        if prefix_rule.get("matchBaseBranches") != EXPECTED_PREFIX_MATCH_BASE:
            errors.append(
                "prefix rule matchBaseBranches must be "
                f"{EXPECTED_PREFIX_MATCH_BASE!r}, got {prefix_rule.get('matchBaseBranches')!r}"
            )
        if prefix_rule.get("commitMessagePrefix") != EXPECTED_COMMIT_MESSAGE_PREFIX:
            errors.append(
                "prefix rule commitMessagePrefix must be "
                f"{EXPECTED_COMMIT_MESSAGE_PREFIX!r}, got {prefix_rule.get('commitMessagePrefix')!r}"
            )

    for policy in MINTMAKER_POLICIES:
        errors.extend(validate_mintmaker_policy(config, package_rules, policy))

    gh_actions_pin = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict)
            and rule.get("matchManagers") == ["github-actions"]
            and rule.get("groupName") == "github-actions"
        ),
        None,
    )
    if gh_actions_pin is None:
        errors.append("missing github-actions group packageRule")
    elif gh_actions_pin.get("pinDigests") is not True:
        errors.append("github-actions group rule must set pinDigests: true")

    if commit_message_prefix_for_branch(config, "main") is not None:
        errors.append("commitMessagePrefix must not apply to base branch 'main'")
    for branch in sorted(RHDS_ENABLED_BRANCHES):
        expected = f"[{branch}]"
        actual = commit_message_prefix_for_branch(config, branch)
        if actual != expected:
            errors.append(
                f"commitMessagePrefix for {branch!r} must be {expected!r}, got {actual!r}"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to renovate.json5 (default: {DEFAULT_CONFIG.relative_to(ROOT)})",
    )
    args = parser.parse_args(argv)
    config_path: Path = args.config.resolve()

    try:
        config = load_config(config_path)
    except (OSError, ValueError, pyjson5.Json5Exception) as exc:
        print(f"error: failed to parse {config_path}: {exc}", file=sys.stderr)
        return 1

    errors = validate_config(config, config_dir=config_path.parent)
    if errors:
        print(f"Renovate config validation failed ({config_path}):", file=sys.stderr)
        for message in errors:
            print(f"  - {message}", file=sys.stderr)
        return 1

    print(f"OK: {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
