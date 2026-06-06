#!/usr/bin/env python3

"""Sync image-tree build args from ``versions_config.yml``.

This flow validates the root config, scans managed image-tree ``build-args``
files, rewrites managed ``BASE_IMAGE`` and ``RELEASE`` assignments plus the
root ``Makefile`` release defaults, resolves newer RHDS ``channel: fast``
releases to the highest already-published phase per target repository, and
uses ``skopeo`` to select the latest build in the chosen release-and-phase
family.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "versions_config.yml"
MANAGED_ROOTS = ("jupyter", "runtimes", "codeserver")
POLICY_SCHEMA = object()

BASE_IMAGE_SCHEMA = {
    "cpu": {
        "rhds": POLICY_SCHEMA,
        "odh": POLICY_SCHEMA,
    },
    "cuda": {
        "minimal": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
        "pytorch": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
        "pytorch-llmcompressor": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
        "tensorflow": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
    },
    "rocm": {
        "minimal": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
        "pytorch": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
        "tensorflow": {
            "rhds": POLICY_SCHEMA,
            "odh": POLICY_SCHEMA,
        },
    },
}

ROOT_SCHEMA = {
    "schema_version": None,
    "release": {
        "full_version": None,
        "rhds_os_base": None,
        "python_version": None,
    },
    "artifacts": {
        "base_image": BASE_IMAGE_SCHEMA,
    },
}

RHDS_CHANNELS = frozenset({"fast", "stable"})
ODH_ORIGINS = frozenset({"in-house", "midstream"})
RHDS_TAG_RE = re.compile(r"^(?P<version>\d+\.\d+\.\d+)(?:-(?P<phase>ea\.\d+))?-(?P<build>\d+)$")
MIDSTREAM_VERSION_RE = re.compile(r"^\d+\.\d+$")
PYTHON_VERSION_RE = re.compile(r"^\d+\.\d+$")
# Sentinel so callers can omit a forward phase; None means GA, not "unset".
_FORWARD_PHASE_UNSET = object()


@dataclass(frozen=True)
class ReleaseConfig:
    full_version: str
    rhds_os_base: str
    python_version: str


@dataclass(frozen=True)
class BaseImagePolicy:
    mode: str
    version: str | None = None


@dataclass(frozen=True)
class VersionsConfig:
    release: ReleaseConfig
    base_image: dict[str, Any]

    def policy(self, accelerator: str, distribution: str, flavor: str | None = None) -> BaseImagePolicy:
        if accelerator == "cpu":
            raw_policy = self.base_image["cpu"][distribution]
        else:
            if flavor is None:
                raise ValueError(f"Flavor is required for accelerator '{accelerator}'")
            raw_policy = self.base_image[accelerator][flavor][distribution]

        key = "channel" if distribution == "rhds" else "origin"
        mode = scalar_to_string(raw_policy[key])
        version_key = policy_version_key(accelerator)
        raw_version = raw_policy.get(version_key)
        version = None if raw_version is None else resolve_version(raw_version, self.release)
        return BaseImagePolicy(mode=mode, version=version)


@dataclass(frozen=True)
class ConfTarget:
    path: Path
    accelerator: str
    distribution: str
    flavor: str | None


@dataclass(frozen=True)
class PlannedUpdate:
    path: Path
    original_text: str
    updated_text: str
    target: ConfTarget | None = None


@dataclass(frozen=True)
class TargetState:
    target: ConfTarget
    original_text: str
    current_base_image: str
    policy: BaseImagePolicy


def scalar_to_string(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int | float):
        return str(value)
    raise TypeError(f"Unsupported scalar value: {value!r}")


def policy_version_key(accelerator: str) -> str:
    return "version" if accelerator == "cpu" else "acc_version"


def resolve_version(value: object, release: ReleaseConfig) -> str:
    resolved = scalar_to_string(value)
    if resolved == "<full_version>":
        return release.full_version
    return resolved


def parse_release_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected semantic version, got '{version}'")
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"Expected semantic version, got '{version}'") from exc


def release_minor_version(full_version: str) -> str:
    major, minor, _patch = parse_release_version(full_version)
    return f"{major}.{minor}"


def parse_minor_version(version: str) -> tuple[int, int]:
    parts = version.split(".")
    if len(parts) != 2:
        raise ValueError(f"Expected major.minor version, got '{version}'")
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"Expected major.minor version, got '{version}'") from exc


def normalize_python_version(version: str) -> str:
    if PYTHON_VERSION_RE.fullmatch(version) is None:
        raise ValueError(f"release.python_version must be in major.minor format, got '{version}'")
    return version


def compact_python_version(version: str) -> str:
    return normalize_python_version(version).replace(".", "")


def hyphenated_python_version(version: str) -> str:
    return normalize_python_version(version).replace(".", "-")


def validate_mapping_schema(data: object, expected: dict[str, Any], context: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {context}")

    actual_keys = set(data)
    expected_keys = set(expected)
    unexpected_keys = sorted(actual_keys - expected_keys)
    missing_keys = sorted(expected_keys - actual_keys)

    if unexpected_keys:
        raise ValueError(f"Unexpected keys under {context}: {', '.join(unexpected_keys)}")
    if missing_keys:
        raise ValueError(f"Missing keys under {context}: {', '.join(missing_keys)}")

    for key, child_schema in expected.items():
        if child_schema is POLICY_SCHEMA:
            continue
        if isinstance(child_schema, dict):
            validate_mapping_schema(data[key], child_schema, f"{context}.{key}")


def validate_version_value(value: object, release: ReleaseConfig, context: str, field_name: str) -> str:
    try:
        resolved = resolve_version(value, release)
    except TypeError as exc:
        raise ValueError(f"Invalid {field_name} at {context}: {exc}") from exc
    if not resolved:
        raise ValueError(f"{field_name} at {context} must not be empty")
    return resolved


def validate_distribution_policy(
    policy: object,
    *,
    distribution: str,
    accelerator: str,
    context: str,
    release: ReleaseConfig,
) -> None:
    if not isinstance(policy, dict):
        raise ValueError(f"Expected mapping at {context}")

    if distribution == "rhds":
        version_key = policy_version_key(accelerator)
        actual_keys = set(policy)
        allowed_keys = {"channel", version_key}
        unexpected_keys = sorted(actual_keys - allowed_keys)
        if unexpected_keys:
            raise ValueError(f"Unexpected keys under {context}: {', '.join(unexpected_keys)}")
        if "channel" not in policy:
            raise ValueError(f"Missing keys under {context}: channel")

        channel = scalar_to_string(policy["channel"])
        if channel not in RHDS_CHANNELS:
            raise ValueError(f"Invalid rhds channel at {context}: {channel}")
        if channel == "fast":
            if version_key not in policy:
                raise ValueError(f"Missing {version_key} for rhds fast channel at {context}")
            validate_version_value(policy[version_key], release, f"{context}.{version_key}", version_key)
        elif version_key in policy:
            raise ValueError(f"rhds stable channel at {context} must not define {version_key}")
        return

    if distribution != "odh":
        raise ValueError(f"Unsupported distribution at {context}: {distribution}")

    version_key = policy_version_key(accelerator)
    actual_keys = set(policy)
    allowed_keys = {"origin", version_key}
    unexpected_keys = sorted(actual_keys - allowed_keys)
    if unexpected_keys:
        raise ValueError(f"Unexpected keys under {context}: {', '.join(unexpected_keys)}")
    if "origin" not in policy:
        raise ValueError(f"Missing keys under {context}: origin")

    origin = scalar_to_string(policy["origin"])
    if origin not in ODH_ORIGINS:
        raise ValueError(f"Invalid odh origin at {context}: {origin}")
    if version_key not in policy:
        raise ValueError(f"Missing {version_key} for odh {origin} origin at {context}")

    version = validate_version_value(policy[version_key], release, f"{context}.{version_key}", version_key)
    normalized_version = normalize_stream_version(version)
    if accelerator == "cpu":
        if version != "latest":
            raise ValueError(f"cpu odh {origin} origin at {context} requires version latest")
        return
    if origin == "midstream" and MIDSTREAM_VERSION_RE.fullmatch(normalized_version) is None:
        raise ValueError(f"odh midstream origin at {context} requires a numeric {version_key}")
    if origin == "in-house" and accelerator != "cpu" and MIDSTREAM_VERSION_RE.fullmatch(normalized_version) is None:
        raise ValueError(f"odh in-house origin at {context} requires a numeric acc_version")


def validate_base_image_config(base_image: dict[str, Any], release: ReleaseConfig) -> None:
    for distribution in ("rhds", "odh"):
        validate_distribution_policy(
            base_image["cpu"][distribution],
            distribution=distribution,
            accelerator="cpu",
            context=f"cpu.{distribution}",
            release=release,
        )

    for accelerator, flavors in (
        ("cuda", ("minimal", "pytorch", "pytorch-llmcompressor", "tensorflow")),
        ("rocm", ("minimal", "pytorch", "tensorflow")),
    ):
        for flavor in flavors:
            for distribution in ("rhds", "odh"):
                validate_distribution_policy(
                    base_image[accelerator][flavor][distribution],
                    distribution=distribution,
                    accelerator=accelerator,
                    context=f"{accelerator}.{flavor}.{distribution}",
                    release=release,
                )


def load_versions_config(path: Path) -> VersionsConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level mapping in {path}")

    validate_mapping_schema(data, ROOT_SCHEMA, "root")

    if data["schema_version"] != 1:
        raise ValueError(f"Unsupported schema_version in {path}: {data['schema_version']!r}")

    release_data = data["release"]
    release = ReleaseConfig(
        full_version=scalar_to_string(release_data["full_version"]),
        rhds_os_base=scalar_to_string(release_data["rhds_os_base"]),
        python_version=scalar_to_string(release_data["python_version"]),
    )
    parse_release_version(release.full_version)
    if not release.rhds_os_base:
        raise ValueError("release.rhds_os_base must not be empty")
    normalize_python_version(release.python_version)

    base_image = data["artifacts"]["base_image"]
    validate_base_image_config(base_image, release)
    return VersionsConfig(release=release, base_image=base_image)


def classify_conf_name(name: str) -> tuple[str, str] | None:
    mapping = {
        "cpu.conf": ("cpu", "odh"),
        "cuda.conf": ("cuda", "odh"),
        "rocm.conf": ("rocm", "odh"),
        "konflux.cpu.conf": ("cpu", "rhds"),
        "konflux.cuda.conf": ("cuda", "rhds"),
        "konflux.rocm.conf": ("rocm", "rhds"),
    }
    return mapping.get(name)


def classify_flavor(relative_path: Path, accelerator: str) -> str | None:
    parts = relative_path.parts

    if accelerator == "cpu":
        if parts[0] in MANAGED_ROOTS:
            return None
        raise ValueError(f"Unsupported CPU build-args path: {relative_path}")

    if accelerator == "cuda":
        if parts[:2] == ("jupyter", "minimal"):
            return "minimal"
        if parts[:2] in {("jupyter", "pytorch"), ("runtimes", "pytorch")}:
            return "pytorch"
        if parts[:2] in {
            ("jupyter", "pytorch+llmcompressor"),
            ("runtimes", "pytorch+llmcompressor"),
        }:
            return "pytorch-llmcompressor"
        if parts[:2] in {("jupyter", "tensorflow"), ("runtimes", "tensorflow")}:
            return "tensorflow"
        raise ValueError(f"Unsupported CUDA build-args path: {relative_path}")

    if accelerator == "rocm":
        if parts[:2] == ("jupyter", "minimal"):
            return "minimal"
        if parts[:3] == ("jupyter", "rocm", "pytorch") or parts[:2] == ("runtimes", "rocm-pytorch"):
            return "pytorch"
        if parts[:3] == ("jupyter", "rocm", "tensorflow") or parts[:2] == ("runtimes", "rocm-tensorflow"):
            return "tensorflow"
        raise ValueError(f"Unsupported ROCm build-args path: {relative_path}")

    raise ValueError(f"Unsupported accelerator '{accelerator}'")


def collect_conf_targets(root_dir: Path) -> list[ConfTarget]:
    targets: list[ConfTarget] = []

    for managed_root in MANAGED_ROOTS:
        search_root = root_dir / managed_root
        if not search_root.is_dir():
            continue

        for path in sorted(search_root.rglob("build-args/*.conf")):
            relative_path = path.relative_to(root_dir)
            classification = classify_conf_name(path.name)
            if classification is None:
                raise ValueError(f"Unsupported build-args filename: {relative_path}")

            accelerator, distribution = classification
            targets.append(
                ConfTarget(
                    path=path,
                    accelerator=accelerator,
                    distribution=distribution,
                    flavor=classify_flavor(relative_path, accelerator),
                )
            )

    return targets


def split_image_ref(image: str) -> tuple[str, str]:
    name, separator, tag = image.rpartition(":")
    if not separator:
        raise ValueError(f"Image reference is missing a tag: {image}")
    return name, tag


def normalize_stream_version(version: str) -> str:
    return version.removeprefix("v")


def build_rhds_family_pattern(candidate_tag: str) -> re.Pattern[str]:
    match = RHDS_TAG_RE.fullmatch(candidate_tag)
    if match is None:
        raise ValueError(f"Unsupported RHDS candidate tag: {candidate_tag}")

    prefix = match.group("version")
    if phase := match.group("phase"):
        prefix = f"{prefix}-{phase}"
    return re.compile(rf"^{re.escape(prefix)}-(?P<build>\d+)$")


def select_latest_matching_rhds_tag(tags: list[str], candidate_tag: str) -> str:
    family_pattern = build_rhds_family_pattern(candidate_tag)
    matches: list[tuple[int, str]] = []

    for tag in tags:
        match = family_pattern.fullmatch(tag)
        if match is None:
            continue
        matches.append((int(match.group("build")), tag))

    if not matches:
        raise ValueError(f"No matching published RHDS tag found for family '{candidate_tag}'")

    return max(matches, key=lambda item: item[0])[1]


def determine_highest_published_rhds_phase_for_release(
    repository: str,
    release_version: str,
    tag_cache: dict[str, tuple[str, ...]] | None = None,
) -> str | None:
    phases: set[str | None] = set()

    for tag in list_rhds_repository_tags(repository, tag_cache):
        match = RHDS_TAG_RE.fullmatch(tag)
        if match is None or match.group("version") != release_version:
            continue
        phases.add(match.group("phase"))

    if not phases:
        return "ea.1"
    return max(phases, key=rank_rhds_phase)


def select_rhds_forward_phase(
    accelerator: str,
    version: str,
    release: ReleaseConfig,
    tag_cache: dict[str, tuple[str, ...]],
) -> str | None:
    repository = build_rhds_pinned_repository(accelerator, version, release)
    return determine_highest_published_rhds_phase_for_release(
        repository,
        release.full_version,
        tag_cache,
    )


def select_highest_published_rhds_tag_for_release(tags: list[str], release_version: str) -> str:
    matches: list[tuple[int, int, str]] = []

    for tag in tags:
        match = RHDS_TAG_RE.fullmatch(tag)
        if match is None or match.group("version") != release_version:
            continue
        matches.append((rank_rhds_phase(match.group("phase")), int(match.group("build")), tag))

    if not matches:
        raise ValueError(f"No published RHDS tags found for release '{release_version}'")

    return max(matches)[2]


def list_rhds_repository_tags(
    repository: str,
    tag_cache: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, ...]:
    if tag_cache is not None and repository in tag_cache:
        return tag_cache[repository]

    try:
        result = subprocess.run(
            ["skopeo", "list-tags", "--retry-times", "3", f"docker://{repository}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("skopeo is required to resolve latest RHDS tags") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
        raise ValueError(f"skopeo list-tags failed for {repository}: {detail}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"skopeo list-tags returned invalid JSON for {repository}") from exc

    tags = payload.get("Tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError(f"skopeo list-tags returned invalid tags for {repository}")

    resolved_tags = tuple(tags)
    if tag_cache is not None:
        tag_cache[repository] = resolved_tags
    return resolved_tags


def resolve_latest_published_rhds_image(
    candidate_image: str,
    tag_cache: dict[str, tuple[str, ...]] | None = None,
) -> str:
    repository, candidate_tag = split_image_ref(candidate_image)
    tags = list(list_rhds_repository_tags(repository, tag_cache))
    try:
        latest_tag = select_latest_matching_rhds_tag(tags, candidate_tag)
    except ValueError:
        match = RHDS_TAG_RE.fullmatch(candidate_tag)
        if match is None or match.group("phase") is not None:
            raise
        latest_tag = select_highest_published_rhds_tag_for_release(tags, match.group("version"))
    return f"{repository}:{latest_tag}"


def build_rhds_pinned_repository(accelerator: str, version: str, release: ReleaseConfig) -> str:
    if accelerator == "cpu":
        return "quay.io/aipcc/base-images/cpu"
    normalized_version = normalize_stream_version(version)
    return f"quay.io/aipcc/base-images/{accelerator}-{normalized_version}-{release.rhds_os_base}"


def describe_rhds_phase(phase: str | None) -> str:
    return "GA" if phase is None else phase


def rank_rhds_phase(phase: str | None) -> int:
    if phase is None:
        return 10_000
    return int(phase.removeprefix("ea."))


def build_rhds_seed_tag(release: ReleaseConfig, phase: str | None) -> str:
    if phase is None:
        return f"{release.full_version}-0"
    return f"{release.full_version}-{phase}-0"


def determine_rhds_fast_bundle_phase(
    states: list[TargetState],
    release: ReleaseConfig,
) -> tuple[bool, str | None]:
    target_version = parse_release_version(release.full_version)
    same_release_phases: set[str | None] = set()

    for peer_state in states:
        if peer_state.target.distribution != "rhds":
            continue
        if peer_state.policy.mode != "fast":
            continue

        _peer_repository, peer_tag = split_image_ref(peer_state.current_base_image)
        match = RHDS_TAG_RE.fullmatch(peer_tag)
        if match is None:
            continue

        peer_version = parse_release_version(match.group("version"))
        if peer_version > target_version:
            continue
        if peer_version == target_version:
            same_release_phases.add(match.group("phase"))

    if not same_release_phases:
        return False, None
    highest_phase = max(same_release_phases, key=rank_rhds_phase)
    return True, highest_phase


def build_rhds_pinned_tag(
    current_tag: str,
    release: ReleaseConfig,
    *,
    use_bundle_phase: bool = False,
    bundle_phase: str | None = None,
    forward_phase: str | None | object = _FORWARD_PHASE_UNSET,
) -> str:
    match = RHDS_TAG_RE.fullmatch(current_tag)
    if match is None:
        raise ValueError(f"Unsupported RHDS BASE_IMAGE tag: {current_tag}")

    current_version = parse_release_version(match.group("version"))
    target_version = parse_release_version(release.full_version)
    build = match.group("build")

    # Phase precedence: rollback -> same-release bundle -> forward-discovered
    # phase -> current tag phase.
    if target_version < current_version:
        phase = None
    elif use_bundle_phase:
        phase = bundle_phase
    elif target_version > current_version:
        phase = "ea.1" if forward_phase is _FORWARD_PHASE_UNSET else forward_phase
    else:
        phase = match.group("phase")

    if phase is None:
        return f"{release.full_version}-{build}"
    return f"{release.full_version}-{phase}-{build}"


def build_rhds_pinned_image(
    accelerator: str,
    version: str,
    current_base_image: str,
    release: ReleaseConfig,
    *,
    use_bundle_phase: bool = False,
    bundle_phase: str | None = None,
    forward_phase: str | None | object = _FORWARD_PHASE_UNSET,
) -> str:
    _current_name, current_tag = split_image_ref(current_base_image)
    repository = build_rhds_pinned_repository(accelerator, version, release)
    return (
        f"{repository}:{build_rhds_pinned_tag(current_tag, release, use_bundle_phase=use_bundle_phase, bundle_phase=bundle_phase, forward_phase=forward_phase)}"
    )


def build_rhds_stable_image(accelerator: str, release: ReleaseConfig) -> str:
    return f"quay.io/aipcc/base-image-{accelerator}-stable-ubi9:{release_minor_version(release.full_version)}"


def build_odh_in_house_image(accelerator: str, version: str, release: ReleaseConfig) -> str:
    repositories = {
        "cpu": f"quay.io/opendatahub/odh-base-image-cpu-py{compact_python_version(release.python_version)}-c9s",
        "cuda": "quay.io/opendatahub/odh-base-image-cuda-py312-c9s",
        "rocm": "quay.io/opendatahub/odh-base-image-rocm-py312-c9s",
    }
    if accelerator not in repositories:
        raise ValueError(f"Unsupported ODH in-house accelerator: {accelerator}")

    if accelerator == "cpu":
        tag = version
    else:
        tag = f"v{normalize_stream_version(version)}"
    return f"{repositories[accelerator]}:{tag}"


def build_odh_midstream_image(accelerator: str, version: str, release: ReleaseConfig) -> str:
    normalized_version = normalize_stream_version(version).replace(".", "-")
    if accelerator == "cpu":
        return f"quay.io/opendatahub/odh-midstream-python-base-{hyphenated_python_version(release.python_version)}:{version}"
    return f"quay.io/opendatahub/odh-midstream-{accelerator}-base-{normalized_version}:latest"


def build_target_base_image(
    state: TargetState,
    release: ReleaseConfig,
    tag_cache: dict[str, tuple[str, ...]],
    rhds_bundle_phase_known: bool,
    rhds_bundle_phase: str | None,
) -> str:
    target = state.target
    current_base_image = state.current_base_image
    policy = state.policy

    if target.distribution == "rhds":
        if policy.mode == "stable":
            return build_rhds_stable_image(target.accelerator, release)
        if policy.version is None:
            raise ValueError(f"Missing {policy_version_key(target.accelerator)} for rhds fast channel in {target.path}")

        _current_repository, current_tag = split_image_ref(current_base_image)
        if RHDS_TAG_RE.fullmatch(current_tag) is None:
            repository = build_rhds_pinned_repository(target.accelerator, policy.version, release)
            if MIDSTREAM_VERSION_RE.fullmatch(current_tag):
                current_minor = parse_minor_version(current_tag)
                target_minor = parse_minor_version(release_minor_version(release.full_version))
                if current_minor > target_minor:
                    seed_phase = None
                elif current_minor < target_minor:
                    seed_phase = select_rhds_forward_phase(
                        target.accelerator,
                        policy.version,
                        release,
                        tag_cache,
                    )
                else:
                    seed_phase = rhds_bundle_phase if rhds_bundle_phase_known else "ea.1"
            else:
                seed_phase = rhds_bundle_phase if rhds_bundle_phase_known else "ea.1"
            candidate = f"{repository}:{build_rhds_seed_tag(release, seed_phase)}"
        else:
            current_match = RHDS_TAG_RE.fullmatch(current_tag)
            forward_phase: str | None | object = _FORWARD_PHASE_UNSET
            current_version = parse_release_version(current_match.group("version"))
            target_version = parse_release_version(release.full_version)
            if target_version > current_version:
                forward_phase = select_rhds_forward_phase(
                    target.accelerator,
                    policy.version,
                    release,
                    tag_cache,
                )
            candidate = build_rhds_pinned_image(
                target.accelerator,
                policy.version,
                current_base_image,
                release,
                use_bundle_phase=rhds_bundle_phase_known and target_version == current_version,
                bundle_phase=rhds_bundle_phase,
                forward_phase=forward_phase,
            )
        return resolve_latest_published_rhds_image(candidate, tag_cache)

    if target.distribution != "odh":
        raise ValueError(f"Unsupported distribution in {target.path}: {target.distribution}")

    if policy.version is None:
        raise ValueError(f"Missing {policy_version_key(target.accelerator)} for odh origin in {target.path}")
    if policy.mode == "in-house":
        return build_odh_in_house_image(target.accelerator, policy.version, release)
    if policy.mode == "midstream":
        return build_odh_midstream_image(target.accelerator, policy.version, release)
    raise ValueError(f"Unsupported odh origin in {target.path}: {policy.mode}")


def read_conf_assignments(text: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        assignments[key.strip()] = value.strip()
    return assignments


def rewrite_conf_text(text: str, replacements: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    found_keys: set[str] = set()
    rewritten_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            rewritten_lines.append(line)
            continue

        key, _, _value = stripped.partition("=")
        normalized_key = key.strip()
        if normalized_key not in replacements:
            rewritten_lines.append(line)
            continue

        found_keys.add(normalized_key)
        line_ending = "\n" if line.endswith("\n") else ""
        rewritten_lines.append(f"{normalized_key}={replacements[normalized_key]}{line_ending}")

    missing_keys = [key for key in replacements if key not in found_keys]
    if missing_keys:
        raise ValueError(f"Missing {', '.join(missing_keys)} in build-args content")
    return "".join(rewritten_lines)


def rewrite_makefile_text(text: str, replacements: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    found_keys: set[str] = set()
    rewritten_lines: list[str] = []
    assignment_re = re.compile(r"^(?P<leading>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<separator>\s*\?=\s*)(?P<value>.*)$")

    for line in lines:
        line_ending = "\n" if line.endswith("\n") else ""
        body = line[:-1] if line_ending else line
        match = assignment_re.fullmatch(body)
        if match is None or match.group("key") not in replacements:
            rewritten_lines.append(line)
            continue

        key = match.group("key")
        found_keys.add(key)
        rewritten_lines.append(
            f"{match.group('leading')}{key}{match.group('separator')}{replacements[key]}{line_ending}"
        )

    missing_keys = [key for key in replacements if key not in found_keys]
    if missing_keys:
        raise ValueError(f"Missing {', '.join(missing_keys)} in Makefile")
    return "".join(rewritten_lines)


def build_conf_replacements(assignments: dict[str, str], resolved_base_image: str, release: ReleaseConfig) -> dict[str, str]:
    replacements = {"BASE_IMAGE": resolved_base_image}
    if "RELEASE" in assignments:
        replacements["RELEASE"] = release_minor_version(release.full_version)
    return replacements


def build_makefile_replacements(release: ReleaseConfig) -> dict[str, str]:
    return {
        "RELEASE": release_minor_version(release.full_version),
        "RELEASE_PYTHON_VERSION": release.python_version,
    }


def plan_updates(root_dir: Path, config: VersionsConfig) -> list[PlannedUpdate]:
    states: list[TargetState] = []
    tag_cache: dict[str, tuple[str, ...]] = {}

    for target in collect_conf_targets(root_dir):
        original_text = target.path.read_text(encoding="utf-8")
        assignments = read_conf_assignments(original_text)
        current_base_image = assignments.get("BASE_IMAGE")
        if current_base_image is None:
            raise ValueError(f"Missing BASE_IMAGE in {target.path}")

        states.append(
            TargetState(
                target=target,
                original_text=original_text,
                current_base_image=current_base_image,
                policy=config.policy(target.accelerator, target.distribution, target.flavor),
            )
        )

    rhds_bundle_phase_known, rhds_bundle_phase = determine_rhds_fast_bundle_phase(states, config.release)

    updates: list[PlannedUpdate] = []
    for state in states:
        resolved_base_image = build_target_base_image(
            state,
            config.release,
            tag_cache,
            rhds_bundle_phase_known,
            rhds_bundle_phase,
        )
        updates.append(
            PlannedUpdate(
                path=state.target.path,
                original_text=state.original_text,
                updated_text=rewrite_conf_text(
                    state.original_text,
                    build_conf_replacements(read_conf_assignments(state.original_text), resolved_base_image, config.release),
                ),
                target=state.target,
            )
        )

    makefile = root_dir / "Makefile"
    if makefile.is_file():
        original_text = makefile.read_text(encoding="utf-8")
        updates.append(
            PlannedUpdate(
                path=makefile,
                original_text=original_text,
                updated_text=rewrite_makefile_text(original_text, build_makefile_replacements(config.release)),
            )
        )

    return updates


def relative_display_path(root_dir: Path, path: Path) -> str:
    return path.relative_to(root_dir).as_posix()


def print_diff(root_dir: Path, update: PlannedUpdate) -> None:
    relative_path = relative_display_path(root_dir, update.path)
    diff = difflib.unified_diff(
        update.original_text.splitlines(),
        update.updated_text.splitlines(),
        fromfile=relative_path,
        tofile=relative_path,
        lineterm="",
    )
    print("\n".join(diff))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DIR, help="Repository root to scan")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to versions_config.yml")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if files need updates")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_versions_config(args.config)
    updates = plan_updates(args.root, config)
    changed_updates = [update for update in updates if update.original_text != update.updated_text]

    if args.dry_run or args.check:
        for update in changed_updates:
            print_diff(args.root, update)
        if changed_updates:
            print(f"{len(changed_updates)} build-args file(s) need updates.")
        else:
            print("Build-args files already match versions_config.yml.")
        return 1 if args.check and changed_updates else 0

    for update in changed_updates:
        update.path.write_text(update.updated_text, encoding="utf-8")
        print(f"Updated {relative_display_path(args.root, update.path)}")

    if not changed_updates:
        print("Build-args files already match versions_config.yml.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
