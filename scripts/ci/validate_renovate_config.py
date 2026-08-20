#!/usr/bin/env python3
"""Validate .github/renovate.json5 syntax and repo-specific semantic invariants."""

from __future__ import annotations

import argparse
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
RHDS_ENABLED_BRANCHES = frozenset({"rhoai-2.25", "rhoai-3.3", "rhoai-3.4", "rhoai-3.5"})
PREFIX_RULE_DESCRIPTION = "Prefix PR titles with branch name for non-main branches"
EXPECTED_PREFIX_MATCH_BASE = ["!/^main$/"]
EXPECTED_COMMIT_MESSAGE_PREFIX = "[{{{baseBranch}}}]"
CENTOS_STREAM_RULE_DESCRIPTION = "Pin CentOS Stream base to stream9 (c9s only; no stream10)"
CENTOS_STREAM_ALLOWED_VERSIONS = "/^stream9$/"
ODH_BASE_DISABLE_RULE_DESCRIPTION = "Disable ODH quay.io/opendatahub BASE_IMAGE updates by default"
ODH_BASE_ENABLE_RULE_DESCRIPTION = "ODH BASE_IMAGE digest updates on opendatahub-io/notebooks main only"
ODH_BASE_MANAGER_DESCRIPTION = "Update BASE_IMAGE in ODH (non-konflux) build-args conf files"
ODH_BASE_MANAGER_FILE_PATTERN = "/(jupyter|codeserver|runtimes)/.+/build-args/(cpu|cuda|rocm)\\.conf$/"
ODH_BASE_PACKAGE_PATTERN = "/^quay\\.io\\/opendatahub\\//"
SEPARATE_MINOR_PATCH_RULE_DESCRIPTION = "Separate minor and patch base image upgrades"


@dataclass(frozen=True)
class MintMakerRepoPolicy:
    label: str
    repository: str
    enabled_branches: frozenset[str]


MINTMAKER_POLICIES = (
    MintMakerRepoPolicy(
        label="ODH",
        repository=ODH_REPO,
        enabled_branches=frozenset({"main"}),
    ),
    MintMakerRepoPolicy(
        label="RHDS",
        repository=RHDS_REPO,
        enabled_branches=RHDS_ENABLED_BRANCHES,
    ),
)

ODH_ENABLED_BRANCHES = MINTMAKER_POLICIES[0].enabled_branches


def load_config(path: Path) -> dict[str, Any]:
    data = pyjson5.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{path}: expected top-level object, got {type(data).__name__}"
        raise ValueError(msg)
    return data


def find_repo_rule(
    package_rules: list[Any],
    repository: str,
    *,
    enabled: bool,
    require_match_base_branches: bool | None = None,
) -> dict[str, Any] | None:
    """Find a repo-wide MintMaker gate rule (no manager/package filters)."""
    for rule in package_rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("matchRepositories") != [repository]:
            continue
        if rule.get("enabled") is not enabled:
            continue
        # Manager-scoped rules (e.g. ODH BASE_IMAGE enable) share matchRepositories
        # with the repo-wide MintMaker gates; only the unscoped gates qualify here.
        if "matchManagers" in rule or "matchPackageNames" in rule:
            continue
        has_match_base_branches = "matchBaseBranches" in rule
        if require_match_base_branches is True and not has_match_base_branches:
            continue
        if require_match_base_branches is False and has_match_base_branches:
            continue
        return rule
    return None


def validate_mintmaker_policy(
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

    return errors


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
        errors.extend(validate_mintmaker_policy(package_rules, policy))

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

    centos_stream_pin = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict) and rule.get("description", "").startswith(CENTOS_STREAM_RULE_DESCRIPTION)
        ),
        None,
    )
    if centos_stream_pin is None:
        errors.append(f"missing CentOS Stream pin packageRule: {CENTOS_STREAM_RULE_DESCRIPTION!r}")
    else:
        if centos_stream_pin.get("matchManagers") != ["dockerfile"]:
            errors.append("CentOS Stream pin rule must match dockerfile manager only")
        if centos_stream_pin.get("matchPackageNames") != ["quay.io/centos/centos"]:
            errors.append("CentOS Stream pin rule must match quay.io/centos/centos only")
        if centos_stream_pin.get("allowedVersions") != CENTOS_STREAM_ALLOWED_VERSIONS:
            errors.append(
                "CentOS Stream pin rule allowedVersions must be "
                f"{CENTOS_STREAM_ALLOWED_VERSIONS!r}, got {centos_stream_pin.get('allowedVersions')!r}"
            )
        if centos_stream_pin.get("pinDigests") is not True:
            errors.append("CentOS Stream pin rule must set pinDigests: true")

    errors.extend(validate_odh_base_image_policy(config.get("customManagers"), package_rules))

    separate_minor_patch_rule = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict) and rule.get("description", "").startswith(SEPARATE_MINOR_PATCH_RULE_DESCRIPTION)
        ),
        None,
    )
    if separate_minor_patch_rule is None:
        errors.append(f"missing packageRule: {SEPARATE_MINOR_PATCH_RULE_DESCRIPTION!r}")
    else:
        if separate_minor_patch_rule.get("matchManagers") != ["custom.regex"]:
            errors.append("separateMinorPatch rule must match custom.regex manager only")
        if separate_minor_patch_rule.get("separateMinorPatch") is not True:
            errors.append("separateMinorPatch rule must set separateMinorPatch: true")

    return errors


def validate_odh_base_image_policy(
    custom_managers: object,
    package_rules: list[Any],
) -> list[str]:
    errors: list[str] = []

    if not isinstance(custom_managers, list):
        errors.append("customManagers must be a list")
        return errors

    odh_manager = next(
        (
            manager
            for manager in custom_managers
            if isinstance(manager, dict) and manager.get("description", "").startswith(ODH_BASE_MANAGER_DESCRIPTION)
        ),
        None,
    )
    if odh_manager is None:
        errors.append(f"missing customManager: {ODH_BASE_MANAGER_DESCRIPTION!r}")
    else:
        patterns = odh_manager.get("managerFilePatterns")
        if patterns != [ODH_BASE_MANAGER_FILE_PATTERN]:
            errors.append(
                "ODH BASE_IMAGE customManager managerFilePatterns must be "
                f"{[ODH_BASE_MANAGER_FILE_PATTERN]!r}, got {patterns!r}"
            )
        if odh_manager.get("versioningTemplate") != "docker":
            errors.append("ODH BASE_IMAGE customManager must use versioningTemplate: docker")

    disable_rule = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict) and rule.get("description", "").startswith(ODH_BASE_DISABLE_RULE_DESCRIPTION)
        ),
        None,
    )
    if disable_rule is None:
        errors.append(f"missing packageRule: {ODH_BASE_DISABLE_RULE_DESCRIPTION!r}")
    else:
        if disable_rule.get("enabled") is not False:
            errors.append("ODH BASE_IMAGE disable rule must set enabled: false")
        if disable_rule.get("matchPackageNames") != [ODH_BASE_PACKAGE_PATTERN]:
            errors.append(
                "ODH BASE_IMAGE disable rule matchPackageNames must be "
                f"{[ODH_BASE_PACKAGE_PATTERN]!r}, got {disable_rule.get('matchPackageNames')!r}"
            )

    enable_rule = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict) and rule.get("description", "").startswith(ODH_BASE_ENABLE_RULE_DESCRIPTION)
        ),
        None,
    )
    if enable_rule is None:
        errors.append(f"missing packageRule: {ODH_BASE_ENABLE_RULE_DESCRIPTION!r}")
    else:
        if enable_rule.get("enabled") is not True:
            errors.append("ODH BASE_IMAGE enable rule must set enabled: true")
        if enable_rule.get("matchRepositories") != [ODH_REPO]:
            errors.append(
                "ODH BASE_IMAGE enable rule matchRepositories must be "
                f"{[ODH_REPO]!r}, got {enable_rule.get('matchRepositories')!r}"
            )
        if enable_rule.get("matchBaseBranches") != ["main"]:
            errors.append(
                "ODH BASE_IMAGE enable rule matchBaseBranches must be ['main'], "
                f"got {enable_rule.get('matchBaseBranches')!r}"
            )
        if enable_rule.get("pinDigests") is not True:
            errors.append("ODH BASE_IMAGE enable rule must set pinDigests: true")
        if enable_rule.get("allowedVersions") != "/^latest$/":
            errors.append(
                "ODH BASE_IMAGE enable rule allowedVersions must be '/^latest$/', "
                f"got {enable_rule.get('allowedVersions')!r}"
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
