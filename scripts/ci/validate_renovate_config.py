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
RHDS_ENABLED_BRANCHES = frozenset({"rhoai-2.25", "rhoai-3.3", "rhoai-3.4", "rhoai-3.5"})
PREFIX_RULE_DESCRIPTION = "Prefix PR titles with branch name for non-main branches"
EXPECTED_PREFIX_MATCH_BASE = ["!/^main$/"]
EXPECTED_COMMIT_MESSAGE_PREFIX = "[{{{baseBranch}}}]"
CENTOS_STREAM_RULE_DESCRIPTION = "Pin CentOS Stream base to stream9 (c9s only; no stream10)"
CENTOS_STREAM_ALLOWED_VERSIONS = "/^stream9$/"
ODH_BASE_DISABLE_RULE_DESCRIPTION = "Disable ODH quay.io/opendatahub BASE_IMAGE updates by default"
ODH_BASE_ENABLE_RULE_DESCRIPTION = "ODH BASE_IMAGE digest updates on opendatahub-io/notebooks main only"
ODH_BASE_TAG_BUMP_BLOCK_RULE_DESCRIPTION = "ODH quay.io/opendatahub: digest-only (no image tag bumps)"
ODH_BASE_GROUP_NAME = "odh BASE_IMAGES"
ODH_BASE_GROUP_SLUG = "odh-base-images"
UPSTREAM_MAIN_MAJOR_MINOR_RULE_DESCRIPTION = "Allow major/minor base image upgrades on upstream main"
KONFLUX_BASE_MANAGER_DESCRIPTION = "Update BASE_IMAGE in konflux build-args conf files"
KONFLUX_BASE_MANAGER_FILE_PATTERN = "/(jupyter|codeserver|runtimes)/.+/build-args/konflux\\..+\\.conf$/"
# Must stay in sync with .github/renovate.json5 (Konflux customManager versioningTemplate).
KONFLUX_AIPCC_VERSIONING_TEMPLATE = (
    "regex:^(?:(?<major>\\d+)\\.(?<minor>\\d+)(?:\\.(?<patch>\\d+))?"
    "(?:-ea\\.(?<prerelease>\\d+-\\d+)|-))?(?<build>\\d+)?$"
)
# Renovate versioningTemplate regex body (after the regex: prefix).
KONFLUX_AIPCC_VERSIONING_REGEX_BODY = KONFLUX_AIPCC_VERSIONING_TEMPLATE.removeprefix("regex:")
KONFLUX_AIPCC_VERSIONING_SAMPLE_TAGS = (
    "1791476595",
    "1791476146",
    "3.6.0-1784563933",
    "3.6.0-1791476877",
    "3.6.0-ea.2-1789501857",
)
ODH_BASE_MANAGER_DESCRIPTION = "Update BASE_IMAGE in ODH (non-konflux) build-args conf files"
ODH_BASE_MANAGER_FILE_PATTERN = "/(jupyter|codeserver|runtimes)/.+/build-args/(cpu|cuda|rocm)\\.conf$/"
ODH_BASE_PACKAGE_PATTERN = "/^quay\\.io\\/opendatahub\\//"
# Same capture names as .github/renovate.json5 customManagers[].matchStrings (Renovate/RE2).
KONFLUX_BASE_IMAGE_MATCH_STRING_RENOVATE = (
    r"BASE_IMAGE=(?<depName>[^:@\s]+(?:/[^:@\s]+)+):(?<currentValue>[^@\s]+)"
    r"(?:@(?<currentDigest>sha256:[a-f0-9]{64}))?"
)
KONFLUX_BASE_IMAGE_MATCH_STRING = re.sub(
    r"\(\?<([a-zA-Z][a-zA-Z0-9]*)>",
    r"(?P<\1>",
    KONFLUX_BASE_IMAGE_MATCH_STRING_RENOVATE,
)
ODH_BASE_IMAGE_SAMPLE_REFS = (
    "quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest@sha256:"
    "9526c7bd09e878d7c08c9de0f96f932435b68858ad9b56493d2cc5c741098ea7",
    "quay.io/opendatahub/odh-base-image-cuda-py312-c9s:v13.0@sha256:"
    "6f8fcdd89279fd7217a53a76b912ff5a563600aff0d16faba15caa8f14600cd7",
    "quay.io/opendatahub/odh-base-image-cuda-py312-c9s:v12.9@sha256:"
    "d474e17631608f1fe52a6137dec87e19878ebdd8541271a85d309736ed4eb59f",
    "quay.io/opendatahub/odh-base-image-rocm-py312-c9s:v7.14@sha256:"
    "b0a89ae435184213d1b01e9c933fddca3da71ac49c577f89d23c7f8d4d4b2b2b",
)
KONFLUX_AIPCC_BASE_IMAGE_SAMPLE_REFS = (
    # Legacy RHAI-style tag on older release branches (e.g. cuda-13.0-el9.8).
    "quay.io/aipcc/base-images/cuda-13.0-el9.8:3.6.0-1791476877@sha256:"
    "47f60de824ea125e16ff3135a78e6f6a3380a9c06648d9b77c8f8cb90335dcac",
    "quay.io/aipcc/base-images/cpu-torch2.13-el9.8:1791476146@sha256:"
    "a494828d82444d3873bf0540bed2ad3f69f1c05e078c76dd418c8574618f3eec",
    "quay.io/aipcc/base-images/cuda13.0-torch2.13-el9.8:1791476595@sha256:"
    "c4b7da6cd0b49ce7a62be010986c6cf745983e68cd408ec054edc74b11b26045",
    "quay.io/aipcc/base-images/cuda12.9-torch2.13-el9.8:1791477182@sha256:"
    "8831a83a1c0360d25fb2e11fc7549ce8ad690a57224b7f998938452bac7b243c",
    "quay.io/aipcc/base-images/rocm7.14-torch2.12-el9.8:1791395349@sha256:"
    "f4d5e421ed54e4f1d1edd4b451387e720620119bdf9e52d74361decb7f25ef8a",
)
RENOVATE_JSON_MAX_LINES = 10
RENOVATE_JSON_SHAPE_ERROR = "renovate.json should include renovate.json5, and nothing else"


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


def _renovate_json_shape_errors(path: Path) -> list[str]:
    """Allow a short JSON wrapper that only includes renovate.json5.

    JSON has no comments. A present file must stay under 10 lines and contain
    only an optional ``$schema`` plus a single ``extends`` entry that includes
    ``renovate.json5``.
    """
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    if len(raw.splitlines()) >= RENOVATE_JSON_MAX_LINES:
        return [RENOVATE_JSON_SHAPE_ERROR]
    try:
        data = pyjson5.loads(raw)
    except pyjson5.Json5Exception:
        return [RENOVATE_JSON_SHAPE_ERROR]
    if not isinstance(data, dict):
        return [RENOVATE_JSON_SHAPE_ERROR]
    if set(data) - {"$schema", "extends"} or "extends" not in data:
        return [RENOVATE_JSON_SHAPE_ERROR]
    extends = data["extends"]
    if isinstance(extends, str):
        extends = [extends]
    if not isinstance(extends, list) or len(extends) != 1:
        return [RENOVATE_JSON_SHAPE_ERROR]
    include = extends[0]
    if not isinstance(include, str) or "renovate.json5" not in include:
        return [RENOVATE_JSON_SHAPE_ERROR]
    return []


def validate_config(config: dict[str, Any], *, config_dir: Path = ROOT / ".github") -> list[str]:
    errors: list[str] = []

    errors.extend(_renovate_json_shape_errors(config_dir / "renovate.json"))

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

    custom_managers = config.get("customManagers")
    errors.extend(validate_konflux_base_image_policy(custom_managers))
    errors.extend(validate_odh_base_image_policy(custom_managers, package_rules))

    return errors


def _renovate_named_group_names(pattern: str) -> list[str]:
    """Return (?<name>…) capture names in source order (Renovate/RE2 syntax)."""
    return re.findall(r"\(\?<([a-zA-Z][a-zA-Z0-9]*)>", pattern)


def _re2_duplicate_named_groups(pattern: str) -> list[str]:
    names = _renovate_named_group_names(pattern)
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


def _konflux_aipcc_tag_matches_versioning(tag: str) -> bool:
    """Approximate Renovate's RE2 template in Python (single <build> capture)."""
    py_pattern = (
        r"^(?:(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?"
        r"(?:-ea\.(?P<prerelease>\d+-\d+)|-))?(?P<build>\d+)?$"
    )
    return re.compile(py_pattern).fullmatch(tag) is not None


def _base_image_match_string_groups(image_ref: str) -> dict[str, str] | None:
    match = re.fullmatch(KONFLUX_BASE_IMAGE_MATCH_STRING, f"BASE_IMAGE={image_ref}")
    if not match:
        return None
    return match.groupdict()


def validate_konflux_base_image_policy(custom_managers: object) -> list[str]:
    errors: list[str] = []

    if not isinstance(custom_managers, list):
        errors.append("customManagers must be a list")
        return errors

    konflux_manager = next(
        (
            manager
            for manager in custom_managers
            if isinstance(manager, dict) and manager.get("description", "").startswith(KONFLUX_BASE_MANAGER_DESCRIPTION)
        ),
        None,
    )
    if konflux_manager is None:
        errors.append(f"missing customManager: {KONFLUX_BASE_MANAGER_DESCRIPTION!r}")
        return errors

    patterns = konflux_manager.get("managerFilePatterns")
    if patterns != [KONFLUX_BASE_MANAGER_FILE_PATTERN]:
        errors.append(
            "Konflux BASE_IMAGE customManager managerFilePatterns must be "
            f"{[KONFLUX_BASE_MANAGER_FILE_PATTERN]!r}, got {patterns!r}"
        )
    if konflux_manager.get("versioningTemplate") != KONFLUX_AIPCC_VERSIONING_TEMPLATE:
        errors.append(
            "Konflux BASE_IMAGE customManager must use versioningTemplate "
            f"{KONFLUX_AIPCC_VERSIONING_TEMPLATE!r}, got {konflux_manager.get('versioningTemplate')!r}"
        )

    if not KONFLUX_AIPCC_VERSIONING_TEMPLATE.startswith("regex:"):
        errors.append("KONFLUX_AIPCC_VERSIONING_TEMPLATE must start with 'regex:'")

    duplicate_groups = _re2_duplicate_named_groups(KONFLUX_AIPCC_VERSIONING_REGEX_BODY)
    if duplicate_groups:
        errors.append(
            "Konflux AIPCC versioningTemplate has duplicate RE2 capture names "
            f"{duplicate_groups!r} (Renovate will reject the config)"
        )

    for tag in KONFLUX_AIPCC_VERSIONING_SAMPLE_TAGS:
        if not _konflux_aipcc_tag_matches_versioning(tag):
            errors.append(f"Konflux AIPCC versioning must accept sample tag {tag!r}")

    match_strings = konflux_manager.get("matchStrings")
    if not isinstance(match_strings, list) or not match_strings:
        errors.append("Konflux BASE_IMAGE customManager must define matchStrings")
    else:
        match_pattern = match_strings[0]
        if not isinstance(match_pattern, str):
            errors.append("Konflux BASE_IMAGE customManager matchStrings[0] must be a string")
        else:
            for image_ref in KONFLUX_AIPCC_BASE_IMAGE_SAMPLE_REFS:
                groups = _base_image_match_string_groups(image_ref)
                if groups is None:
                    errors.append(
                        f"Konflux BASE_IMAGE matchStrings must parse sample ref {image_ref!r}"
                    )
                    continue
                tag = groups.get("currentValue")
                if not isinstance(tag, str) or not _konflux_aipcc_tag_matches_versioning(tag):
                    errors.append(
                        f"Konflux BASE_IMAGE tag {tag!r} from {image_ref!r} must match versioningTemplate"
                    )

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

        match_strings = odh_manager.get("matchStrings")
        if not isinstance(match_strings, list) or not match_strings:
            errors.append("ODH BASE_IMAGE customManager must define matchStrings")
        elif isinstance(match_strings[0], str):
            for image_ref in ODH_BASE_IMAGE_SAMPLE_REFS:
                if _base_image_match_string_groups(image_ref) is None:
                    errors.append(
                        f"ODH BASE_IMAGE matchStrings must parse sample ref {image_ref!r}"
                    )

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
        if "allowedVersions" in enable_rule:
            errors.append(
                "ODH BASE_IMAGE enable rule must not set allowedVersions "
                "(blocks CUDA/ROCm versioned tags; digest updates use pinDigests)"
            )
        if "matchUpdateTypes" in enable_rule:
            errors.append(
                "ODH BASE_IMAGE enable rule must not set matchUpdateTypes "
                "(Renovate leaves quay.io/opendatahub deps disabled at lookup)"
            )
        if enable_rule.get("groupName") != ODH_BASE_GROUP_NAME:
            errors.append(
                f"ODH BASE_IMAGE enable rule groupName must be {ODH_BASE_GROUP_NAME!r}, "
                f"got {enable_rule.get('groupName')!r}"
            )
        if enable_rule.get("groupSlug") != ODH_BASE_GROUP_SLUG:
            errors.append(
                f"ODH BASE_IMAGE enable rule groupSlug must be {ODH_BASE_GROUP_SLUG!r}, "
                f"got {enable_rule.get('groupSlug')!r}"
            )
        if enable_rule.get("separateMajorMinor") is not False:
            errors.append("ODH BASE_IMAGE enable rule must set separateMajorMinor: false")
        if enable_rule.get("separateMinorPatch") is not False:
            errors.append("ODH BASE_IMAGE enable rule must set separateMinorPatch: false")

    tag_block_rule = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict)
            and rule.get("description", "").startswith(ODH_BASE_TAG_BUMP_BLOCK_RULE_DESCRIPTION)
        ),
        None,
    )
    if tag_block_rule is None:
        errors.append(f"missing packageRule: {ODH_BASE_TAG_BUMP_BLOCK_RULE_DESCRIPTION!r}")
    else:
        if tag_block_rule.get("enabled") is not False:
            errors.append("ODH tag-bump block rule must set enabled: false")
        if tag_block_rule.get("matchUpdateTypes") != ["major", "minor", "patch"]:
            errors.append(
                "ODH tag-bump block rule matchUpdateTypes must be ['major', 'minor', 'patch'], "
                f"got {tag_block_rule.get('matchUpdateTypes')!r}"
            )
        if tag_block_rule.get("matchRepositories") != [ODH_REPO]:
            errors.append(
                "ODH tag-bump block rule matchRepositories must be "
                f"{[ODH_REPO]!r}, got {tag_block_rule.get('matchRepositories')!r}"
            )
        if tag_block_rule.get("matchBaseBranches") != ["main"]:
            errors.append(
                "ODH tag-bump block rule matchBaseBranches must be ['main'], "
                f"got {tag_block_rule.get('matchBaseBranches')!r}"
            )

    upstream_major_minor = next(
        (
            rule
            for rule in package_rules
            if isinstance(rule, dict)
            and rule.get("description", "").startswith(UPSTREAM_MAIN_MAJOR_MINOR_RULE_DESCRIPTION)
        ),
        None,
    )
    if upstream_major_minor is not None:
        names = upstream_major_minor.get("matchPackageNames")
        if names != ["!/^quay\\.io\\/opendatahub\\//"]:
            errors.append(
                "upstream main major/minor rule must exclude quay.io/opendatahub "
                f"(matchPackageNames), got {names!r}"
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
