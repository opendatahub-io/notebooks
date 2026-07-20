#!/usr/bin/env python3
"""Extract PEP 517 build-system.requires transitively from sdists on PyPI.

For each pinned package in requirements.cpu.txt, downloads its sdist (if one
exists), reads the root pyproject.toml, and collects build-system.requires.
Then recursively resolves build deps of build deps until no new packages are
discovered.

Build backends often have empty build-system.requires (e.g. hatchling
self-bootstraps via backend-path) but still need their project.dependencies
installed when built/used from sdist. Those install deps can themselves be
sdists with their own build-system.requires (hatchling → trove-classifiers →
calver). So for every package discovered as a build dep, we also follow its
project.dependencies to continue the closure — still seeded only from the
runtime lockfile.

Usage:
    python3 extract-build-deps.py requirements.cpu.txt
"""

import io
import json
import sys
import tarfile
import tomllib
import urllib.request
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

# Normalized name → /pypi/{name}/json payload (avoids a second metadata fetch
# when a package was just resolved via get_latest_version).
_pypi_project_cache: dict[str, dict] = {}


def fetch_pypi_project(name: str) -> dict | None:
    key = canonicalize_name(name)
    if key in _pypi_project_cache:
        return _pypi_project_cache[key]
    try:
        resp = urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: pypi {name}: {e}", file=sys.stderr)
        return None
    _pypi_project_cache[key] = data
    return data


def get_latest_version(name: str) -> str | None:
    data = fetch_pypi_project(name)
    return data["info"]["version"] if data else None


def is_root_pyproject(path: str) -> bool:
    """Match only <sdist-root>/pyproject.toml, not nested fixtures/tests."""
    parts = path.replace("\\", "/").split("/")
    return path == "pyproject.toml" or (len(parts) == 2 and parts[1] == "pyproject.toml")


def read_pyproject_meta(content: bytes) -> tuple[list[str], list[str]]:
    toml = tomllib.loads(content.decode())
    build_requires = toml.get("build-system", {}).get("requires") or []
    project_deps = toml.get("project", {}).get("dependencies") or []
    return build_requires, project_deps


def _sdist_files(name: str, version: str) -> list[dict]:
    """Return PyPI file records for an sdist of name==version."""
    cached = _pypi_project_cache.get(canonicalize_name(name))
    if cached and version in cached.get("releases", {}):
        return cached["releases"][version]

    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: {name}=={version}: {e}", file=sys.stderr)
        return []
    return data.get("urls", [])


def extract_sdist_meta(name: str, version: str) -> tuple[list[str], list[str]]:
    """Return (build-system.requires, project.dependencies) from the sdist root pyproject."""
    sdist_urls = [u for u in _sdist_files(name, version) if u.get("packagetype") == "sdist"]
    if not sdist_urls:
        return [], []

    sdist_url = sdist_urls[0]["url"]
    sdist_filename = sdist_urls[0]["filename"]

    try:
        sdist_data = urllib.request.urlopen(sdist_url, timeout=30).read()
    except Exception as e:
        print(f"  WARN: download {name}=={version}: {e}", file=sys.stderr)
        return [], []

    try:
        if sdist_filename.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(sdist_data), mode="r:gz") as tf:
                for m in tf.getmembers():
                    if is_root_pyproject(m.name):
                        fobj = tf.extractfile(m)
                        if fobj:
                            return read_pyproject_meta(fobj.read())
        elif sdist_filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(sdist_data)) as zf:
                for zname in zf.namelist():
                    if is_root_pyproject(zname):
                        return read_pyproject_meta(zf.read(zname))
    except Exception as e:
        print(f"  WARN: parse {name}=={version}: {e}", file=sys.stderr)

    return [], []


def parse_requirements_file(path: str) -> dict[str, str]:
    packages: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" not in line:
                continue
            try:
                req = Requirement(line.split("\\")[0].strip())
            except Exception:
                continue
            for spec in req.specifier:
                if spec.operator == "==":
                    packages[canonicalize_name(req.name)] = spec.version
                    break
    return packages


def req_name(req_str: str) -> str | None:
    try:
        return canonicalize_name(Requirement(req_str).name)
    except Exception:
        return None


def enqueue_new(
    dep_name: str,
    seen: set[str],
    next_round: list[tuple[str, str]],
    *,
    kind: str,
) -> None:
    if dep_name in seen:
        return
    dep_version = get_latest_version(dep_name)
    if not dep_version:
        return
    seen.add(dep_name)
    next_round.append((dep_name, dep_version))
    print(f"    -> {kind}: {dep_name}=={dep_version}")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} requirements.cpu.txt", file=sys.stderr)
        sys.exit(1)

    runtime_pinned = parse_requirements_file(sys.argv[1])
    to_process: list[tuple[str, str]] = list(runtime_pinned.items())
    seen: set[str] = set(runtime_pinned)
    all_build_dep_names: set[str] = set()

    iteration = 0
    while to_process:
        iteration += 1
        next_round: list[tuple[str, str]] = []
        print(f"\n=== Iteration {iteration}: processing {len(to_process)} packages ===")

        for name, version in to_process:
            build_requires, project_deps = extract_sdist_meta(name, version)

            if build_requires:
                print(f"  {name}=={version} build-system.requires: {build_requires}")

            for req_str in build_requires:
                dep_name = req_name(req_str)
                if not dep_name:
                    continue
                all_build_dep_names.add(dep_name)
                enqueue_new(dep_name, seen, next_round, kind="new build dep")

            # Build-only packages: follow install deps to find their build-system.requires.
            if name not in runtime_pinned and project_deps:
                print(f"  {name}=={version} project.dependencies: {project_deps}")
                for req_str in project_deps:
                    dep_name = req_name(req_str)
                    if dep_name:
                        enqueue_new(
                            dep_name, seen, next_round, kind="build-backend install dep"
                        )

        to_process = next_round

    print(f"\n=== Unique build dep package names ({len(all_build_dep_names)}) ===")
    print("# Paste into requirements-build.in:")
    for dep in sorted(all_build_dep_names):
        print(dep)


if __name__ == "__main__":
    main()
