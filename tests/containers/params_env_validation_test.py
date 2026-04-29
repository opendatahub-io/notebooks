"""Validate params.env and commit.env image references against actual registry metadata.

Replaces the shell script ``ci/check-params-env.sh`` with structured pytest output.
Uses ``skopeo inspect`` to fetch image labels and sizes from the registry, then
compares against expected values from ``ci/expected-image-metadata.yaml``.

Tests are marked ``manifest_validation`` and excluded from default collection.
Run explicitly::

    pytest tests/containers/params_env_validation_test.py -v
    pytest tests/containers/ -m manifest_validation -v
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml

from tests import PROJECT_ROOT

if TYPE_CHECKING:
    import pathlib

    import pytest_subtests

_LOG = logging.getLogger(__name__)

_BASE_DIRS = [PROJECT_ROOT / "manifests" / "odh" / "base", PROJECT_ROOT / "manifests" / "rhoai" / "base"]
_VARIANTS = {"odh": _BASE_DIRS[0], "rhoai": _BASE_DIRS[1]}
_METADATA_PATH = PROJECT_ROOT / "ci" / "expected-image-metadata.yaml"

# Size change thresholds (matching the shell script)
_SIZE_PERCENT_THRESHOLD = 10
_SIZE_ABSOLUTE_THRESHOLD_MB = 100

# skopeo retry count
_SKOPEO_RETRY = 3


def _parse_env(env_path: pathlib.Path) -> dict[str, str]:
    """Parse a KEY=VALUE env file into a dict."""
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if key and value:
            result[key.strip()] = value.strip()
    return result


def _load_expected_metadata() -> dict[str, dict]:
    """Load expected image metadata from YAML."""
    return yaml.safe_load(_METADATA_PATH.read_text())


def _resolve_expected(entry: dict, variant: str, field: str):
    """Resolve a field that may be variant-specific (dict) or shared (scalar)."""
    val = entry.get(field)
    if isinstance(val, dict):
        return val.get(variant)
    return val


def _skopeo_inspect_config(image_url: str) -> dict | None:
    """Run skopeo inspect --config and return parsed JSON."""
    try:
        result = subprocess.run(
            [
                "skopeo",
                "inspect",
                "--retry-times",
                str(_SKOPEO_RETRY),
                "--override-arch",
                "amd64",
                "--override-os",
                "linux",
                "--config",
                f"docker://{image_url}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        _LOG.warning(f"skopeo inspect --config failed for {image_url}: {exc}")
        return None


def _skopeo_inspect_raw(image_url: str) -> dict | None:
    """Run skopeo inspect --raw and return parsed JSON."""
    try:
        result = subprocess.run(
            [
                "skopeo",
                "inspect",
                "--retry-times",
                str(_SKOPEO_RETRY),
                "--override-arch",
                "amd64",
                "--override-os",
                "linux",
                "--raw",
                f"docker://{image_url}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        _LOG.warning(f"skopeo inspect --raw failed for {image_url}: {exc}")
        return None


def _get_image_size_mb(image_url: str) -> int | None:
    """Get compressed image size in MB via skopeo inspect --raw."""
    raw = _skopeo_inspect_raw(image_url)
    if raw is None:
        return None

    # Try direct layer sizes (single-arch image)
    layers = raw.get("layers", [])
    if layers:
        total = sum(layer.get("size", 0) for layer in layers)
        return total // (1024 * 1024)

    # Multi-arch: resolve amd64 manifest
    manifests = raw.get("manifests", [])
    amd64 = next(
        (
            m
            for m in manifests
            if m.get("platform", {}).get("os") == "linux" and m.get("platform", {}).get("architecture") == "amd64"
        ),
        None,
    )
    if amd64 is None:
        return None

    base = image_url.rsplit("@", 1)[0]
    # Strip tag but not port (port has a / after the colon, tag doesn't)
    if "/" not in base.rsplit(":", 1)[-1]:
        base = base.rsplit(":", 1)[0]
    platform_raw = _skopeo_inspect_raw(f"{base}@{amd64['digest']}")
    if platform_raw is None:
        return None

    layers = platform_raw.get("layers", [])
    total = sum(layer.get("size", 0) for layer in layers)
    return total // (1024 * 1024)


def _strip_version_suffix(variable: str) -> str:
    """Strip the version/tag suffix from a params.env variable name.

    'odh-workbench-jupyter-minimal-cpu-py312-ubi9-2025-2' → 'odh-workbench-jupyter-minimal-cpu-py312-ubi9'
    'odh-workbench-jupyter-minimal-cpu-py312-ubi9-n'      → 'odh-workbench-jupyter-minimal-cpu-py312-ubi9'
    """
    return re.sub(r"-(\d{4}-\d+|n.*)$", "", variable)


def _strip_os_suffix(name: str) -> str:
    """Strip OS suffix (-ubi9, -rhel9, -c9s) from a name."""
    return re.sub(r"-(ubi9|rhel9|c9s)$", "", name)


def _extract_repo_name(image_url: str) -> str:
    """Extract the repository name from an image URL, stripping tag/digest and OS suffix.

    quay.io/.../odh-workbench-jupyter-minimal-cpu-py312-ubi9@sha256:abc → odh-workbench-jupyter-minimal-cpu-py312
    registry.redhat.io/rhoai/odh-workbench-...-py312-rhel9@sha256:abc  → odh-workbench-...-py312
    quay.io/.../odh-pipeline-runtime-minimal-cpu-py312-ubi9:3.5_ea1    → odh-pipeline-runtime-minimal-cpu-py312
    """
    last = image_url.rsplit("/", maxsplit=1)[-1]
    name = last.split("@")[0].split(":")[0]
    return _strip_os_suffix(name)


def _find_commit_value(variable: str, commit_entries: dict[str, str]) -> str | None:
    """Find the commit.env value matching a params.env variable.

    commit.env keys insert ``-commit`` before the version suffix::

        params.env: odh - workbench - ... - ubi9 - 2025 - 2
        commit.env: odh - workbench - ... - ubi9 - commit - 2025 - 2
    """
    for ck, cv in commit_entries.items():
        if ck.replace("-commit", "") == variable:
            return cv
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.manifest_validation
@pytest.mark.parametrize("base_dir", _BASE_DIRS, ids=["odh", "rhoai"])
def test_params_env_variable_uniqueness(
    subtests: pytest_subtests.SubTests,
    base_dir: pathlib.Path,
):
    """All variable names in params.env + params-latest.env are unique."""
    for env_name in ["params", "commit"]:
        files = [base_dir / f"{env_name}.env", base_dir / f"{env_name}-latest.env"]
        all_keys: list[str] = []
        all_values: list[str] = []
        for f in files:
            if not f.exists():
                continue
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, value = line.partition("=")
                if key and value:
                    all_keys.append(key.strip())
                    all_values.append(value.strip())

        with subtests.test(msg=f"{env_name}.env variable name uniqueness"):
            seen: dict[str, int] = {}
            for k in all_keys:
                seen[k] = seen.get(k, 0) + 1
            dups = {k: v for k, v in seen.items() if v > 1}
            assert not dups, f"Duplicate variable names in {env_name}.env: {dups}"

        if env_name == "params":
            non_dummy = [v for v in all_values if v != "dummy"]
            with subtests.test(msg=f"{env_name}.env value uniqueness"):
                seen_vals: dict[str, int] = {}
                for v in non_dummy:
                    seen_vals[v] = seen_vals.get(v, 0) + 1
                dups = {k: v for k, v in seen_vals.items() if v > 1}
                assert not dups, f"Duplicate image refs in {env_name}.env: {dups}"


@pytest.mark.manifest_validation
@pytest.mark.parametrize("base_dir", _BASE_DIRS, ids=["odh", "rhoai"])
def test_params_env_record_count(
    subtests: pytest_subtests.SubTests,
    base_dir: pathlib.Path,
):
    """Expected number of entries in env files."""
    variant = "rhoai" if "rhoai" in str(base_dir) else "odh"
    expected_counts = {
        "odh": {"commit": 39, "params": 33},
        "rhoai": {"commit": 39, "params": 39},
    }

    for env_name, expected in expected_counts[variant].items():
        files = [base_dir / f"{env_name}.env", base_dir / f"{env_name}-latest.env"]
        total = sum(len(_parse_env(f)) for f in files)
        with subtests.test(msg=f"{env_name}.env record count"):
            assert total == expected, (
                f"Expected {expected} records in {env_name}.env + {env_name}-latest.env, got {total}"
            )


@pytest.mark.manifest_validation
@pytest.mark.parametrize("base_dir", _BASE_DIRS, ids=["odh", "rhoai"])
def test_params_env_image_metadata(
    subtests: pytest_subtests.SubTests,
    base_dir: pathlib.Path,
):
    """Each image in params.env has correct labels, commit ID, repo name, and size."""
    if not shutil.which("skopeo"):
        pytest.skip("skopeo not found on PATH")

    variant = "rhoai" if "rhoai" in str(base_dir) else "odh"
    expected_metadata = _load_expected_metadata()

    # Load commit.env for commit ID validation
    commit_entries = {**_parse_env(base_dir / "commit.env"), **_parse_env(base_dir / "commit-latest.env")}

    for env_file in [base_dir / "params.env", base_dir / "params-latest.env"]:
        # Skip RHOAI params-latest.env (dummy placeholders)
        if variant == "rhoai" and env_file.name == "params-latest.env":
            continue

        params = _parse_env(env_file)
        for variable, image_url in params.items():
            if image_url == "dummy":
                continue

            _LOG.info(f"Checking {variable}: {image_url}")

            config = _skopeo_inspect_config(image_url)
            if config is None:
                with subtests.test(msg=f"{variable}: skopeo inspect"):
                    pytest.fail(f"Could not inspect {image_url}")
                continue

            labels = config.get("config", {}).get("Labels", {})

            # --- Detect build system ---
            is_konflux = "io.openshift.build.commit.id" not in labels

            if is_konflux:
                commit_id = labels.get("vcs-ref", "")

                # Repo name check (no YAML needed)
                with subtests.test(msg=f"{variable}: repo name"):
                    var_stripped = _strip_os_suffix(_strip_version_suffix(variable))
                    repo_name = _extract_repo_name(image_url)
                    assert var_stripped == repo_name, f"Repo name '{repo_name}' doesn't match variable '{var_stripped}'"
            else:
                commit_id = labels.get("io.openshift.build.commit.id", "")

            # --- Commit ID check (no YAML needed) ---
            if commit_id and "odh-pipeline-runtime-" not in variable:
                file_commit = _find_commit_value(variable, commit_entries)
                if file_commit:
                    short_commit = commit_id[:7]
                    with subtests.test(msg=f"{variable}: commit ID"):
                        assert short_commit == file_commit, (
                            f"Image commit '{short_commit}' != commit.env '{file_commit}'"
                        )

            # --- YAML-dependent checks below ---
            expected = expected_metadata.get(variable)
            if expected is None:
                with subtests.test(msg=f"{variable}: metadata entry"):
                    pytest.fail("Not in ci/expected-image-metadata.yaml")
                continue

            with subtests.test(msg=f"{variable}: variant allow-list"):
                assert variant in expected.get("variants", []), (
                    f"{variable} is not declared for the {variant} manifests"
                )
            if variant not in expected.get("variants", []):
                continue

            # Check image name label
            expected_name = _resolve_expected(expected, variant, "name")
            actual_name = labels.get("name")
            if expected_name:
                with subtests.test(msg=f"{variable}: image name"):
                    assert actual_name == expected_name, f"Expected name '{expected_name}', got '{actual_name}'"

            # Check commitref (OpenShift-CI only)
            if not is_konflux:
                commitref = labels.get("io.openshift.build.commit.ref", "")
                expected_commitref = expected.get("commitref", "")
                if expected_commitref:
                    with subtests.test(msg=f"{variable}: commitref"):
                        assert commitref == expected_commitref, (
                            f"Expected commitref '{expected_commitref}', got '{commitref}'"
                        )

            # Check image size
            expected_size = _resolve_expected(expected, variant, "size_mb")
            if expected_size:
                actual_size = _get_image_size_mb(image_url)
                if actual_size is None:
                    with subtests.test(msg=f"{variable}: image size fetch"):
                        pytest.fail(f"Could not determine size for {image_url}")
                else:
                    with subtests.test(msg=f"{variable}: image size"):
                        percent_change = abs(100 * actual_size // expected_size - 100)
                        abs_change = abs(actual_size - expected_size)
                        assert percent_change <= _SIZE_PERCENT_THRESHOLD or abs_change <= _SIZE_ABSOLUTE_THRESHOLD_MB, (
                            f"Size {actual_size}MB vs expected {expected_size}MB "
                            f"(change: {percent_change}%, {abs_change}MB)"
                        )
