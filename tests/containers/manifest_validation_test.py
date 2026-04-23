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

import collections
import dataclasses
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import packaging.utils
import packaging.version
import pytest
import yaml

from manifests.tools.commit_env_refs import parse_env_file
from manifests.tools.package_names import manifest_name_to_pip
from tests import PROJECT_ROOT

if TYPE_CHECKING:
    import pytest_subtests

_LOG = logging.getLogger(__name__)

# Software annotation items that cannot be validated from SBOM data.
_SKIP_SOFTWARE: frozenset[str] = frozenset()

# Packages listed in manifest annotations that are not pip packages.
_NON_PIP_PACKAGES: frozenset[str] = frozenset(
    {
        "rstudio-server",
    }
)


def _imagestream_to_source_hint(is_name: str) -> str:
    """Derive SBOM sourceInfo path fragment from imagestream filename.

    SBOMs aggregate packages from a source-repo scan (all Pipfile.lock files in the
    monorepo) and an image-filesystem scan.  When the same pypi package appears in
    multiple Pipfile.lock files with different versions, we prefer the one whose
    sourceInfo matches the notebook type implied by the imagestream name.
    """
    stem = is_name.removesuffix("-imagestream.yaml")
    if stem.startswith("jupyter-"):
        middle = stem.removeprefix("jupyter-").removesuffix("-notebook")
        middle = middle.replace("pytorch-llmcompressor", "pytorch+llmcompressor")
        middle = middle.removesuffix("-gpu")
        if middle.startswith("rocm-"):
            middle = middle.replace("rocm-", "rocm/", 1)
        return f"/jupyter/{middle}/"
    if stem.startswith("code-server"):
        return "/codeserver/"
    if stem.startswith("rstudio"):
        return "/rstudio/"
    if stem.startswith("runtime-"):
        middle = stem.removeprefix("runtime-")
        middle = middle.replace("pytorch-llmcompressor", "pytorch+llmcompressor")
        return f"/runtimes/{middle}/"
    return ""


def _extract_python_version(image_ref: str) -> str:
    """Extract Python minor version from image reference.

    Example: ``...py311...`` -> ``3.11``, ``...py312...`` -> ``3.12``.
    """
    m = re.search(r"py(\d)(\d+)", image_ref)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return ""


def _normalize_pip_name(name: str) -> str:
    """Normalize pip package name per PEP 503."""
    return packaging.utils.canonicalize_name(name)


# ---------------------------------------------------------------------------
# pytest options
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Multi-arch resolution
# ---------------------------------------------------------------------------


def _resolve_amd64(image_ref: str) -> str:
    """Resolve a multi-arch manifest list to the amd64 image digest.

    If *image_ref* already points to a single-arch image, returns it unchanged.
    Requires ``skopeo`` on PATH.
    """
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
            raise RuntimeError(f"No amd64 manifest in {image_ref}")
        base = image_ref.rsplit("@", 1)[0]
        return f"{base}@{amd64}"
    return image_ref


# ---------------------------------------------------------------------------
# Package extraction backends
# ---------------------------------------------------------------------------


def _packages_from_sbom(image_ref: str, *, source_hint: str = "", python_version: str = "") -> dict[str, str]:
    """Extract {normalized_name: version} from the SBOM attached to *image_ref*.

    For multi-arch manifest lists, resolves the amd64 image first.
    Requires ``cosign`` and ``skopeo`` on PATH.

    SBOMs for workbench images are generated by squashing two Syft runs (source
    repo scan + image filesystem scan).  The source scan picks up every
    Pipfile.lock in the monorepo, so the same pypi package can appear multiple
    times with different versions.  *source_hint* and *python_version* are used
    to disambiguate duplicates — see :func:`_resolve_pypi_duplicates`.
    """
    image_ref = _resolve_amd64(image_ref)

    result = subprocess.run(
        ["cosign", "download", "sbom", image_ref],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    sbom = json.loads(result.stdout)

    packages: dict[str, str] = {}
    pypi_entries: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)

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
            source_info = pkg.get("sourceInfo", "")
            pypi_entries[_normalize_pip_name(name)].append((version, source_info))
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

    packages.update(_resolve_pypi_duplicates(pypi_entries, source_hint, python_version))
    return packages


def _resolve_pypi_duplicates(
    pypi_entries: dict[str, list[tuple[str, str]]],
    source_hint: str,
    python_version: str,
) -> dict[str, str]:
    """Pick the best version for each pypi package when the SBOM has duplicates.

    Resolution chain (first match wins):

    1. **Python version filter** — drop entries whose ``sourceInfo`` refers to
       a different Python minor version (e.g. keep ``python-3.11``, drop
       ``python-3.12``).
    2. **Source-hint match** — prefer the entry whose ``sourceInfo`` contains
       *source_hint* (e.g. ``/jupyter/trustyai/``).
    3. **Datascience hierarchy fallback** — prefer ``/jupyter/datascience/``
       (common parent for all jupyter notebook types).
    4. **Highest version** — heuristic tie-breaker.
    """
    result: dict[str, str] = {}
    for name, entries in pypi_entries.items():
        if len(entries) == 1:
            result[name] = entries[0][0]
            continue

        candidates = entries

        # Step 1: filter by Python version
        if python_version:
            py_filtered = [
                (v, s) for v, s in candidates if f"python-{python_version}" in s or f"python{python_version}" in s
            ]
            if py_filtered:
                candidates = py_filtered
        if len(candidates) == 1:
            result[name] = candidates[0][0]
            continue

        # Step 2: prefer source matching the notebook type
        if source_hint:
            matching = [v for v, s in candidates if source_hint in s]
            if matching:
                result[name] = matching[0]
                continue

        # Step 3: hierarchy fallback — prefer datascience parent
        ds = [v for v, s in candidates if "/jupyter/datascience/" in s]
        if ds:
            result[name] = ds[0]
            continue

        # Step 4: highest version tie-breaker
        try:
            candidates = sorted(
                candidates,
                key=lambda e: packaging.version.Version(e[0].split("+")[0]),
                reverse=True,
            )
        except packaging.version.InvalidVersion:
            pass
        result[name] = candidates[0][0]

    return result


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
    pip_name = _normalize_pip_name(manifest_name_to_pip(name))
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
            lookup = manifest_name
            actual_version_str = _resolve_software_version(dep, actual_packages)
        else:
            if manifest_name in _NON_PIP_PACKAGES:
                continue
            lookup = _normalize_pip_name(manifest_name_to_pip(manifest_name))
            actual_version_str = actual_packages.get(lookup)

        if actual_version_str is None:
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
    params = parse_env_file(base_dir / "params.env")
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
    """Fast: validate N-1 tag annotations against SBOM artifacts (cosign + skopeo, no image pull).

    The SBOM is generated by squashing two Syft runs: a source-repo scan (all
    Pipfile.lock files in the monorepo) and an image-filesystem scan.  The
    source scan produces the bulk of pypi entries; the image scan contributes
    RPMs and a handful of pip packages whose dist-info was not already covered
    by a lockfile (site-packages entries are mostly missing from the scan).

    Because every Pipfile.lock in the monorepo ends up in the SBOM, the same
    pip package often appears multiple times with different versions.
    ``_resolve_pypi_duplicates`` disambiguates using the Python version and
    notebook-type source hint, but the heuristic is not perfect — for some
    packages it picks a version that differs from what is actually installed
    (e.g. tensorboard in pytorch images).  Prefer ``test_old_tag_annotations_match_quay``
    when an authoritative per-image check is needed.
    """
    if not shutil.which("cosign") or not shutil.which("skopeo"):
        pytest.skip("cosign and/or skopeo not found on PATH")

    for t in _iter_old_tags(base_dir):
        _LOG.info(f"Fetching SBOM for {t.is_name} tag {t.tag_name}: {t.image_ref}")
        if "quay.io/modh/" in t.image_ref:
            _LOG.info(f"Skipping pre-Konflux image (no SBOM): {t.image_ref}")
            continue

        source_hint = _imagestream_to_source_hint(t.is_name)
        python_version = _extract_python_version(t.image_ref)
        try:
            actual_packages = _packages_from_sbom(t.image_ref, source_hint=source_hint, python_version=python_version)
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


# ---------------------------------------------------------------------------
# Quay.io Clair backend
# ---------------------------------------------------------------------------


def _get_quay_auth() -> str | None:
    """Extract quay.io Basic auth from container registry config files.

    Also checks the ``QUAY_AUTH`` environment variable (base64-encoded
    ``user:password``), which takes precedence over config files.
    """
    env_auth = os.environ.get("QUAY_AUTH")
    if env_auth:
        return env_auth

    for path in [
        pathlib.Path.home() / ".docker" / "config.json",
        pathlib.Path.home() / ".config" / "containers" / "auth.json",
    ]:
        if not path.exists():
            continue
        try:
            config = json.loads(path.read_text())
            auth = config.get("auths", {}).get("quay.io", {}).get("auth")
            if auth:
                return auth
        except json.JSONDecodeError, OSError:
            continue
    return None


def _image_ref_to_quay(image_ref: str) -> tuple[str, str]:
    """Map an image reference to a Quay.io (repo, digest) pair.

    Handles ``registry.redhat.io/rhoai/X@sha256:abc``,
    ``quay.io/modh/X@sha256:abc``, etc.
    """
    # Strip the registry prefix and split off the digest
    ref, _, digest = image_ref.partition("@")
    if not digest:
        raise ValueError(f"Image reference has no digest: {image_ref}")

    # registry.redhat.io/rhoai/X → rhoai/X (same repo name on quay.io)
    if ref.startswith("registry.redhat.io/"):
        repo = ref.removeprefix("registry.redhat.io/")
    elif ref.startswith("quay.io/"):
        repo = ref.removeprefix("quay.io/")
    else:
        raise ValueError(f"Cannot map to quay.io: {image_ref}")

    return repo, digest


def _packages_from_quay(image_ref: str, quay_auth: str) -> dict[str, str]:
    """Extract {normalized_name: version} from Quay.io Clair security scan.

    Clair scans each OCI layer independently, so the same package can appear
    multiple times with different versions.  We resolve duplicates by
    preferring the version from the topmost (last) layer, using the
    ``AddedBy`` field (compressed layer digest) matched against the image
    manifest's layer list.

    Requires ``skopeo`` on PATH for multi-arch resolution and layer ordering.
    """
    image_ref = _resolve_amd64(image_ref)

    # Get layer order from the image manifest for duplicate resolution.
    # Clair's AddedBy matches the compressed layer digests from the manifest,
    # not the uncompressed DiffIDs from the image config.
    raw = subprocess.run(
        ["skopeo", "inspect", "--raw", f"docker://{image_ref}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    manifest = json.loads(raw.stdout)
    layer_order: dict[str, int] = {layer["digest"]: i for i, layer in enumerate(manifest.get("layers", []))}

    repo, digest = _image_ref_to_quay(image_ref)
    url = f"https://quay.io/api/v1/repository/{repo}/manifest/{digest}/security?vulnerabilities=false"

    req = urllib.request.Request(url, headers={"Authorization": f"Basic {quay_auth}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    features = data.get("data", {}).get("Layer", {}).get("Features", [])
    if not features:
        status = data.get("status")
        if status in {"queued", "scanning"}:
            raise RuntimeError(f"Clair scan not ready for {image_ref} (status={status})")
        raise RuntimeError(f"No features in Clair response for {image_ref}")

    # Collect all entries keyed by both rpm: and normalized-pip forms,
    # tracking layer index for disambiguation.
    entries: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    for feat in features:
        name = feat.get("Name", "")
        version = feat.get("Version", "")
        if not name or not version:
            continue

        # Skip Go modules and Java artifacts
        if "github.com/" in name or ":" in name:
            continue

        layer_idx = layer_order.get(feat.get("AddedBy", ""), -1)
        entries[f"rpm:{name}"].append((version, layer_idx))
        entries[_normalize_pip_name(name)].append((version, layer_idx))

    # Resolve: for duplicates, prefer the version from the topmost layer.
    packages: dict[str, str] = {}
    for key, versions in entries.items():
        if len(versions) == 1:
            packages[key] = versions[0][0]
        else:
            packages[key] = max(versions, key=lambda v: v[1])[0]

    # On RHEL 9 the system Python 3.9 RPM is named "python3" (not "python39").
    # _resolve_software_version looks for "rpm:python3.9", so add an alias.
    if "rpm:python3" in packages:
        py3_ver = packages["rpm:python3"]
        m = re.match(r"(\d+\.\d+)", py3_ver)
        if m:
            packages[f"rpm:python{m.group(1)}"] = py3_ver

    # On RHEL 8 the Python 3.8 RPM is named "python38" (no dot).
    # _resolve_software_version looks for "rpm:python3.8", so add an alias.
    if "rpm:python38" in packages:
        py38_ver = packages["rpm:python38"]
        m = re.match(r"(\d+\.\d+)", py38_ver)
        if m:
            packages[f"rpm:python{m.group(1)}"] = py38_ver

    return packages


@pytest.mark.manifest_validation
@pytest.mark.parametrize("base_dir", _BASE_DIRS, ids=["odh", "rhoai"])
def test_old_tag_annotations_match_quay(
    subtests: pytest_subtests.SubTests,
    base_dir: pathlib.Path,
):
    """Validate N-1 tag annotations against Quay.io Clair security scan data."""
    quay_auth = _get_quay_auth()
    if quay_auth is None:
        pytest.skip("No quay.io auth found in ~/.docker/config.json or ~/.config/containers/auth.json")
    if not shutil.which("skopeo"):
        pytest.skip("skopeo not found on PATH")

    for t in _iter_old_tags(base_dir):
        _LOG.info(f"Fetching Quay packages for {t.is_name} tag {t.tag_name}: {t.image_ref}")
        try:
            actual_packages = _packages_from_quay(t.image_ref, quay_auth)
        except (
            RuntimeError,
            ValueError,
            urllib.error.URLError,
            json.JSONDecodeError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as exc:
            with subtests.test(msg=f"{t.is_name} tag {t.tag_name}: Quay fetch"):
                pytest.fail(f"Failed to fetch Quay packages for {t.image_ref}: {exc}")
            continue

        _compare_manifest_vs_actual(subtests, t.is_name, t.tag_name, t.python_deps, actual_packages)
        # Clair cannot resolve code-server (npm package with 0.0.0 dev version).
        quay_software = [sw for sw in t.software if sw["name"] != "code-server"]
        _compare_manifest_vs_actual(subtests, t.is_name, t.tag_name, quay_software, actual_packages, is_software=True)
