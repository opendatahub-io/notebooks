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
import re
import sys
import tarfile
import tomllib
import urllib.request
import zipfile

from packaging.requirements import Requirement


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def get_latest_version(name: str) -> str | None:
    try:
        resp = urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=10)
        data = json.loads(resp.read())
        return data["info"]["version"]
    except Exception:
        return None


def is_root_pyproject(path: str) -> bool:
    """Match only <sdist-root>/pyproject.toml, not nested fixtures/tests."""
    parts = path.replace("\\", "/").split("/")
    return path == "pyproject.toml" or (len(parts) == 2 and parts[1] == "pyproject.toml")


def read_pyproject_meta(content: bytes) -> tuple[list[str], list[str]]:
    toml = tomllib.loads(content.decode())
    build_requires = toml.get("build-system", {}).get("requires", []) or []
    project_deps = toml.get("project", {}).get("dependencies", []) or []
    return build_requires, project_deps


def extract_sdist_meta(name: str, version: str) -> tuple[list[str], list[str]]:
    """Return (build-system.requires, project.dependencies) from the sdist root pyproject."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        print(f"  WARN: {name}=={version}: {e}", file=sys.stderr)
        return [], []

    data = json.loads(resp.read())
    sdist_urls = [u for u in data.get("urls", []) if u["packagetype"] == "sdist"]
    if not sdist_urls:
        return [], []

    sdist_url = sdist_urls[0]["url"]
    sdist_filename = sdist_urls[0]["filename"]

    try:
        resp2 = urllib.request.urlopen(sdist_url, timeout=30)
        sdist_data = resp2.read()
    except Exception as e:
        print(f"  WARN: download {name}=={version}: {e}", file=sys.stderr)
        return [], []

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
                    packages[normalize(req.name)] = spec.version
                    break
    return packages


def enqueue_new(
    dep_name: str,
    seen: set[str],
    next_round: list[tuple[str, str]],
    *,
    as_build_dep: bool,
) -> None:
    if dep_name in seen:
        return
    seen.add(dep_name)
    dep_version = get_latest_version(dep_name)
    if not dep_version:
        return
    next_round.append((dep_name, dep_version))
    kind = "new build dep" if as_build_dep else "build-backend install dep"
    print(f"    -> {kind}: {dep_name}=={dep_version}")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} requirements.cpu.txt", file=sys.stderr)
        sys.exit(1)

    runtime_pinned = parse_requirements_file(sys.argv[1])
    runtime_names = set(runtime_pinned.keys())

    to_process: list[tuple[str, str]] = list(runtime_pinned.items())
    seen: set[str] = set(runtime_names)
    all_build_dep_names: set[str] = set()

    iteration = 0
    while to_process:
        iteration += 1
        next_round: list[tuple[str, str]] = []
        print(f"\n=== Iteration {iteration}: processing {len(to_process)} packages ===")

        for name, version in to_process:
            build_requires, project_deps = extract_sdist_meta(name, version)
            is_build_package = name not in runtime_names

            if build_requires:
                print(f"  {name}=={version} build-system.requires: {build_requires}")

            for req_str in build_requires:
                try:
                    req = Requirement(req_str)
                except Exception:
                    continue
                dep_name = normalize(req.name)
                all_build_dep_names.add(dep_name)
                enqueue_new(dep_name, seen, next_round, as_build_dep=True)

            # Follow install deps of build backends / build-only packages so we
            # discover *their* build-system.requires (e.g. hatchling →
            # trove-classifiers → calver). Runtime packages' install deps are
            # already in requirements.cpu.txt.
            if is_build_package and project_deps:
                print(f"  {name}=={version} project.dependencies: {project_deps}")
                for req_str in project_deps:
                    try:
                        req = Requirement(req_str)
                    except Exception:
                        continue
                    enqueue_new(
                        normalize(req.name),
                        seen,
                        next_round,
                        as_build_dep=False,
                    )

        to_process = next_round

    print(f"\n=== Unique build dep package names ({len(all_build_dep_names)}) ===")
    print("# Paste into requirements-build.in:")
    for dep in sorted(all_build_dep_names):
        print(dep)


if __name__ == "__main__":
    main()
