"""Validate that imagestream manifest annotations match actual package versions in shipped images.

The N-1 (and older) tag annotations in imagestream YAML files declare package versions
like ``{"name": "Odh-Elyra", "version": "5.0"}``. These tests verify that the annotations
match reality by checking what's actually installed in the shipped images.

Two approaches are provided:

- **SBOM-based** (fast, ~2s per image): downloads the SBOM artifact attached to the image
  via ``cosign download sbom``, no need to pull the full image. Works when cosign+skopeo
  are available. For multi-arch images, resolves the amd64 manifest first.

- **pip-list-based** (slow, pulls full image): starts a container and runs ``pip list``.
  Requires a container runtime (podman/docker). More thorough but much slower for large
  CUDA/ROCm images. Cleans up images it pulled (but not pre-existing ones).
  Use ``--no-cleanup-images`` to disable cleanup.

Both tests are marked ``manifest_validation`` and excluded from default collection
(``tests/containers/`` is not in ``testpaths``). Run explicitly::

    pytest tests/containers/manifest_validation_test.py -v
    pytest tests/containers/ -m manifest_validation -v

This catches bugs like PR #3185, which upgraded Elyra to 5.0 on the N tag but also
incorrectly bumped the N-1 annotation to 5.0, even though the N-1 image still had 4.3.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import packaging.version
import pytest
import yaml

from tests import PROJECT_ROOT

if TYPE_CHECKING:
    import pathlib

    import pytest_subtests

_LOG = logging.getLogger(__name__)

# Translation from manifest display names to pip package names.
_MANIFEST_TO_PIP: dict[str, str] = {
    "LLM-Compressor": "llmcompressor",
    "PyTorch": "torch",
    "ROCm-PyTorch": "torch",
    "Sklearn-onnx": "skl2onnx",
    "Nvidia-CUDA-CU12-Bundle": "nvidia-cuda-runtime-cu12",
    "MySQL Connector/Python": "mysql-connector-python",
    "TensorFlow-ROCm": "tensorflow-rocm",
}

# Software annotation items that cannot be validated from SBOM data.
_SKIP_SOFTWARE: frozenset[str] = frozenset()

# Packages listed in manifest annotations that are not pip packages.
_NON_PIP_PACKAGES: frozenset[str] = frozenset(
    {
        "rstudio-server",
    }
)

# Manifest names where .lower() gives the pip name.
_MANIFEST_LOWER_NAMES: frozenset[str] = frozenset(
    {
        "Accelerate",
        "Boto3",
        "Codeflare-SDK",
        "Datasets",
        "Feast",
        "JupyterLab",
        "Kafka-Python-ng",
        "Kfp",
        "Kubeflow-Training",
        "Matplotlib",
        "Numpy",
        "Odh-Elyra",
        "Pandas",
        "Psycopg",
        "PyMongo",
        "Pyodbc",
        "Scikit-learn",
        "Scipy",
        "TensorFlow",
        "Tensorboard",
        "Torch",
        "Transformers",
        "TrustyAI",
        "TensorFlow-ROCm",
        "MLflow",
    }
)


def _manifest_name_to_pip(name: str) -> str:
    """Convert a manifest display name to a pip package name."""
    if name in _MANIFEST_TO_PIP:
        return _MANIFEST_TO_PIP[name]
    if name in _MANIFEST_LOWER_NAMES:
        return name.lower()
    return name


def _normalize_pip_name(name: str) -> str:
    """Normalize pip package name per PEP 503 (lowercase, hyphens)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_params_env(env_path: pathlib.Path) -> dict[str, str]:
    """Parse params.env into {key: image_reference}."""
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


# ---------------------------------------------------------------------------
# pytest options
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Package extraction backends
# ---------------------------------------------------------------------------


def _packages_from_sbom(image_ref: str) -> dict[str, str]:
    """Extract {normalized_name: version} from the SBOM attached to *image_ref*.

    For multi-arch manifest lists, resolves the amd64 image first.
    Requires ``cosign`` and ``skopeo`` on PATH.
    """
    # Resolve multi-arch → amd64 digest
    raw = subprocess.run(
        ["skopeo", "inspect", "--raw", f"docker://{image_ref}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    manifest = json.loads(raw.stdout)
    if "manifests" in manifest:
        amd64 = next(
            (m["digest"] for m in manifest["manifests"] if m.get("platform", {}).get("architecture") == "amd64"),
            None,
        )
        if amd64 is None:
            pytest.skip(f"No amd64 manifest in {image_ref}")
        # Replace digest in the ref
        base = image_ref.rsplit("@", 1)[0]
        image_ref = f"{base}@{amd64}"

    result = subprocess.run(
        ["cosign", "download", "sbom", image_ref],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    sbom = json.loads(result.stdout)

    packages: dict[str, str] = {}
    for pkg in sbom.get("packages", []):
        refs = pkg.get("externalRefs", [])
        purl = next(
            (r.get("referenceLocator", "") for r in refs if "purl" in r.get("referenceType", "")),
            "",
        )
        name = pkg.get("name", "")
        version = pkg.get("versionInfo", "")
        if not name or not version or version == "UNKNOWN":
            continue
        if "pkg:pypi/" in purl:
            packages[_normalize_pip_name(name)] = version
        elif "pkg:rpm/" in purl:
            # Store RPM packages for software annotation validation
            # e.g. python3.12=3.12.12-1.el9, cuda-nvcc-12-8=12.8.93-1, rocm-core=6.4.3...
            packages[f"rpm:{name}"] = version
        elif "pkg:npm/" in purl:
            key = f"npm:{name}"
            # npm SBOMs can have multiple versions of the same package
            # (nested node_modules). We only look up code-server, so just
            # keep whichever entry isn't 0.0.0 (dev placeholder).
            if key not in packages or packages[key] == "0.0.0":
                packages[key] = version
    return packages


def _exec_or_none(container: object, cmd: list[str]) -> str | None:
    """Run a command in a container, return stdout or None on failure."""
    try:
        ecode, output = container.exec(cmd)
        if ecode == 0:
            return output.decode().strip()
    except Exception:
        pass
    return None


def _collect_software_versions(container: object, packages: dict[str, str]) -> None:
    """Populate *packages* with software versions obtained by running commands in *container*.

    This makes ``_resolve_software_version`` work for the pip-list backend by providing
    the same ``rpm:*`` / ``npm:*`` keys that the SBOM backend produces.
    """
    # Python — "Python 3.12.8"
    out = _exec_or_none(container, ["python3", "--version"])
    if out:
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        if m:
            packages[f"rpm:python{m.group(1).rsplit('.', 1)[0]}"] = m.group(1)

    # CUDA — "Cuda compilation tools, release 12.9, V12.9.86"
    # Runtime images may not have nvcc; fall back to cuda-cudart RPM query
    out = _exec_or_none(container, ["nvcc", "--version"])
    if out:
        m = re.search(r"release (\d+)\.(\d+)", out)
        if m:
            packages[f"rpm:cuda-nvcc-{m.group(1)}-{m.group(2)}"] = f"{m.group(1)}.{m.group(2)}"
    else:
        out = _exec_or_none(
            container, ["/bin/bash", "-c", "rpm -qa 'cuda-cudart-[0-9]*' --queryformat '%{NAME} %{VERSION}\\n'"]
        )
        if out:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 2:
                    packages[f"rpm:{parts[0]}"] = parts[1]

    # ROCm — "6.4.3.60403"
    out = _exec_or_none(container, ["rpm", "-q", "--queryformat", "%{VERSION}", "rocm-core"])
    if out and "not installed" not in out:
        packages["rpm:rocm-core"] = out

    # R — "R version 4.5.0 (2025-04-11)"
    out = _exec_or_none(container, ["R", "--version"])
    if out:
        m = re.search(r"R version (\d+\.\d+\.\d+)", out)
        if m:
            packages["rpm:R-core"] = m.group(1)

    # rstudio-server
    out = _exec_or_none(container, ["rpm", "-q", "--queryformat", "%{VERSION}", "rstudio-server"])
    if out and "not installed" not in out:
        packages["rpm:rstudio-server"] = out

    # code-server --version outputs e.g. "0.0.0 <hash> with Code 1.104.0"
    # The "1.104.0" is the internal VS Code version; _resolve_software_version
    # maps it to the release version "4.104" for manifest comparison.
    out = _exec_or_none(container, ["code-server", "--version"])
    if out:
        m = re.search(r"with Code (\d+\.\d+\.\d+)", out)
        if m:
            packages["npm:code-server"] = m.group(1)


def _packages_from_pip_list(image_ref: str, *, cleanup: bool) -> dict[str, str]:
    """Extract {normalized_name: version} by running ``pip list`` inside a container.

    If the image was not present locally before this call and *cleanup* is True,
    the image is removed after inspection to free disk space.
    """
    import docker  # noqa: PLC0415
    import docker.errors  # noqa: PLC0415
    import testcontainers.core.container  # noqa: PLC0415

    from tests.containers import docker_utils  # noqa: PLC0415

    client = docker.from_env()

    # Check if image is already present locally
    was_present = True
    try:
        client.images.get(image_ref)
    except docker.errors.ImageNotFound:
        was_present = False

    container = testcontainers.core.container.DockerContainer(image=image_ref, user=23456, group_add=[0])
    container.with_command("/bin/sh -c 'sleep infinity'")
    try:
        container.start()
        ecode, output = container.exec(["python3", "-m", "pip", "list", "--format", "json"])
        assert ecode == 0, f"pip list failed in {image_ref}: {output.decode()}"
        pkgs = json.loads(output.decode())
        packages = {_normalize_pip_name(p["name"]): p["version"] for p in pkgs}

        # Collect software versions via commands inside the container.
        # These populate the same dict so _resolve_software_version can find them.
        _collect_software_versions(container, packages)

        return packages
    finally:
        docker_utils.NotebookContainer(container).stop(timeout=0)
        if not was_present and cleanup:
            try:
                client.images.remove(image_ref, force=True)
                _LOG.info(f"Cleaned up pulled image {image_ref}")
            except Exception as exc:
                _LOG.warning(f"Failed to remove image {image_ref}: {exc}")


# ---------------------------------------------------------------------------
# Common validation logic
# ---------------------------------------------------------------------------


def _check_major_minor(manifest_version: str, actual_version_str: str) -> tuple[bool, str]:
    """Compare major.minor of manifest version against actual. Returns (matches, reason)."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)", manifest_version)
    if not m:
        return False, f"unparseable manifest version: {manifest_version!r}"
    expected_mm = (int(m.group(1)), int(m.group(2)))
    # Strip RPM release suffix (e.g. "3.12.12-1.el9" → "3.12.12") and local version ("+cu128")
    clean = actual_version_str.split("-", maxsplit=1)[0].split("+", maxsplit=1)[0]
    # Handle RPM epoch-style versions like "6.4.3.60403" — take first two segments
    parts = clean.split(".")
    if len(parts) >= 2:
        try:
            actual_mm = (int(parts[0]), int(parts[1]))
            return actual_mm == expected_mm, f"{actual_mm} vs {expected_mm}"
        except ValueError:
            pass
    try:
        actual_ver = packaging.version.Version(clean)
        actual_mm = (actual_ver.major, actual_ver.minor)
        return actual_mm == expected_mm, f"{actual_mm} vs {expected_mm}"
    except packaging.version.InvalidVersion:
        return False, f"unparseable actual version: {actual_version_str!r}"


def _resolve_software_version(sw_item: dict[str, str], actual_packages: dict[str, str]) -> str | None:
    """Look up the actual version for a notebook-software item from SBOM data.

    Returns the version string if found, None otherwise.
    """
    name = sw_item["name"]
    version = sw_item.get("version", "")

    if name == "Python":
        # Match python3.XX RPM — find the one matching the expected minor version
        m = re.fullmatch(r"v?(\d+)\.(\d+)", version)
        if m:
            rpm_name = f"rpm:python{m.group(1)}.{m.group(2)}"
            return actual_packages.get(rpm_name)
        return None

    if name == "CUDA":
        # Extract CUDA version from RPM *name*, not the RPM version field.
        # Rogue compat packages like cuda-cudart-11-7 coexist with the real
        # toolkit (RHAIENG-354). We parse "rpm:cuda-nvcc-12-9" → "12.9".
        # Priority: cuda-nvcc (compiler) > cuda-cudart (runtime).
        # Pick highest version to skip rogue old compat libs.
        best: packaging.version.Version | None = None
        best_str = ""
        for prefix in ("rpm:cuda-nvcc-", "rpm:cuda-cudart-"):
            for key in actual_packages:
                if not key.startswith(prefix):
                    continue
                ver_str = key[len(prefix) :].replace("-", ".")
                try:
                    ver = packaging.version.Version(ver_str)
                except packaging.version.InvalidVersion:
                    continue
                if best is None or ver > best:
                    best = ver
                    best_str = ver_str
            if best_str:
                return best_str  # return as soon as a preferred prefix matches
        return None

    if name == "ROCm":
        return actual_packages.get("rpm:rocm-core")

    if name == "R":
        return actual_packages.get("rpm:R-core")

    if name == "rstudio-server":
        return actual_packages.get("rpm:rstudio-server")

    if name == "code-server":
        # The manifest uses code-server release version (e.g. "4.104") while the
        # npm SBOM reports the internal VS Code server version (e.g. "1.104.0").
        # The minor component (104) corresponds between both schemes.
        npm_ver = actual_packages.get("npm:code-server")
        if npm_ver and npm_ver != "0.0.0":
            # Rewrite npm version to match manifest scheme: "1.104.0" → "4.104"
            parts = npm_ver.split(".")
            if len(parts) >= 2:
                return f"4.{parts[1]}"
        return None

    # PyTorch, TensorFlow, LLM-Compressor, etc. — look up as pip package
    pip_name = _normalize_pip_name(_manifest_name_to_pip(name))
    return actual_packages.get(pip_name)


def _compare_manifest_vs_actual(
    subtests: pytest_subtests.SubTests,
    is_name: str,
    tag_name: str,
    expected_deps: list[dict[str, str]],
    actual_packages: dict[str, str],
    *,
    is_software: bool = False,
) -> None:
    """Compare manifest annotation deps against actual package versions.

    When *is_software* is True, uses software-specific resolution (RPM, CUDA, ROCm).
    Otherwise uses pip package resolution.
    """
    for dep in expected_deps:
        manifest_name = dep["name"]
        manifest_version = dep.get("version", "")

        if is_software:
            if manifest_name in _SKIP_SOFTWARE:
                continue
            actual_version_str = _resolve_software_version(dep, actual_packages)
        else:
            if manifest_name in _NON_PIP_PACKAGES:
                continue
            pip_name = _normalize_pip_name(_manifest_name_to_pip(manifest_name))
            actual_version_str = actual_packages.get(pip_name)

        if actual_version_str is None:
            lookup = manifest_name if is_software else _normalize_pip_name(_manifest_name_to_pip(manifest_name))
            with subtests.test(msg=f"{is_name} tag {tag_name}: {manifest_name} not found"):
                pytest.fail(
                    f"Manifest lists {manifest_name} ({lookup}) v{manifest_version} but it was not found in the image"
                )
            continue

        matches, _reason = _check_major_minor(manifest_version, actual_version_str)
        if not matches:
            with subtests.test(
                msg=f"{is_name} tag {tag_name}: {manifest_name} {manifest_version} != {actual_version_str}"
            ):
                pytest.fail(f"Manifest says {manifest_name}=={manifest_version}, but image has {actual_version_str}")


@dataclasses.dataclass
class _TagInfo:
    is_name: str
    tag_name: str
    image_ref: str
    python_deps: list[dict[str, str]]
    software: list[dict[str, str]]


def _iter_old_tags(base_dir: pathlib.Path) -> list[_TagInfo]:
    """Yield tag info for every non-recommended tag (N-1, N-2, ...) with a params.env entry."""
    params = _parse_params_env(base_dir / "params.env")
    if not params:
        return []

    results = []
    for is_file in sorted(base_dir.glob("*-imagestream.yaml")):
        is_data = yaml.safe_load(is_file.read_text())
        is_name = is_file.name

        if is_data["metadata"].get("labels", {}).get("opendatahub.io/runtime-image") == "true":
            continue

        tags = is_data["spec"]["tags"]
        # tags[0] is the recommended/latest (N) tag — skip it
        for tag in tags[1:]:
            tag_name = tag["name"]
            placeholder = tag["from"]["name"]
            param_key = placeholder.removesuffix("_PLACEHOLDER")
            image_ref = params.get(param_key)

            if not image_ref or image_ref == "dummy":
                continue

            deps_json = tag["annotations"].get("opendatahub.io/notebook-python-dependencies", "[]")
            sw_json = tag["annotations"].get("opendatahub.io/notebook-software", "[]")

            results.append(
                _TagInfo(
                    is_name=is_name,
                    tag_name=tag_name,
                    image_ref=image_ref,
                    python_deps=json.loads(deps_json),
                    software=json.loads(sw_json),
                )
            )
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

_BASE_DIRS = [PROJECT_ROOT / "manifests" / "odh" / "base", PROJECT_ROOT / "manifests" / "rhoai" / "base"]


@pytest.mark.manifest_validation
@pytest.mark.parametrize("base_dir", _BASE_DIRS, ids=["odh", "rhoai"])
def test_old_tag_annotations_match_sbom(
    subtests: pytest_subtests.SubTests,
    base_dir: pathlib.Path,
):
    """Fast: validate N-1 tag annotations against SBOM artifacts (cosign + skopeo, no image pull)."""
    if not shutil.which("cosign") or not shutil.which("skopeo"):
        pytest.skip("cosign and/or skopeo not found on PATH")

    for t in _iter_old_tags(base_dir):
        _LOG.info(f"Fetching SBOM for {t.is_name} tag {t.tag_name}: {t.image_ref}")
        if "quay.io/modh/" in t.image_ref:
            _LOG.info(f"Skipping pre-Konflux image (no SBOM): {t.image_ref}")
            continue

        try:
            actual_packages = _packages_from_sbom(t.image_ref)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            with subtests.test(msg=f"{t.is_name} tag {t.tag_name}: SBOM fetch"):
                pytest.fail(f"Failed to fetch SBOM for {t.image_ref}: {exc}")
            continue

        _compare_manifest_vs_actual(subtests, t.is_name, t.tag_name, t.python_deps, actual_packages)
        _compare_manifest_vs_actual(subtests, t.is_name, t.tag_name, t.software, actual_packages, is_software=True)


@pytest.mark.manifest_validation
@pytest.mark.parametrize("base_dir", _BASE_DIRS, ids=["odh", "rhoai"])
def test_old_tag_annotations_match_image_content(
    subtests: pytest_subtests.SubTests,
    base_dir: pathlib.Path,
    request: pytest.FixtureRequest,
):
    """Slow: validate N-1 tag annotations by running pip list inside the actual container."""
    cleanup = not request.config.getoption("--no-cleanup-images", default=False)

    for t in _iter_old_tags(base_dir):
        _LOG.info(f"Pulling and inspecting {t.is_name} tag {t.tag_name}: {t.image_ref}")
        actual_packages = _packages_from_pip_list(t.image_ref, cleanup=cleanup)
        _compare_manifest_vs_actual(subtests, t.is_name, t.tag_name, t.python_deps, actual_packages)
        _compare_manifest_vs_actual(subtests, t.is_name, t.tag_name, t.software, actual_packages, is_software=True)
