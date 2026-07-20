#!/usr/bin/env python3
"""Extract PEP 517 build-system.requires transitively from sdists on PyPI.

For each pinned package in a requirements.txt, downloads its sdist (if one
exists), reads pyproject.toml, and collects build deps. Then recursively
resolves build deps of build deps until no new packages are discovered.

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


def extract_build_requires(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        print(f"  WARN: {name}=={version}: {e}", file=sys.stderr)
        return []

    data = json.loads(resp.read())
    sdist_urls = [u for u in data.get("urls", []) if u["packagetype"] == "sdist"]
    if not sdist_urls:
        return []

    sdist_url = sdist_urls[0]["url"]
    sdist_filename = sdist_urls[0]["filename"]

    try:
        resp2 = urllib.request.urlopen(sdist_url, timeout=30)
        sdist_data = resp2.read()
    except Exception as e:
        print(f"  WARN: download {name}=={version}: {e}", file=sys.stderr)
        return []

    def read_pyproject(content: bytes) -> list[str]:
        toml = tomllib.loads(content.decode())
        return toml.get("build-system", {}).get("requires", [])

    if sdist_filename.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(sdist_data), mode="r:gz") as tf:
            for m in tf.getmembers():
                if m.name.endswith("/pyproject.toml") or m.name == "pyproject.toml":
                    fobj = tf.extractfile(m)
                    if fobj:
                        return read_pyproject(fobj.read())
    elif sdist_filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(sdist_data)) as zf:
            for zname in zf.namelist():
                if zname.endswith("/pyproject.toml") or zname == "pyproject.toml":
                    return read_pyproject(zf.read(zname))

    return []


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


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} requirements.txt [requirements-build.cpu.txt ...]", file=sys.stderr)
        sys.exit(1)

    pinned: dict[str, str] = {}
    for reqs_file in sys.argv[1:]:
        pinned.update(parse_requirements_file(reqs_file))

    to_process: list[tuple[str, str]] = list(pinned.items())
    seen: set[str] = set(pinned.keys())
    all_build_dep_names: set[str] = set()

    iteration = 0
    while to_process:
        iteration += 1
        next_round: list[tuple[str, str]] = []
        print(f"\n=== Iteration {iteration}: processing {len(to_process)} packages ===")

        for name, version in to_process:
            requires = extract_build_requires(name, version)
            if not requires:
                continue

            print(f"  {name}=={version}: {requires}")

            for req_str in requires:
                try:
                    req = Requirement(req_str)
                except Exception:
                    continue

                dep_name = normalize(req.name)
                all_build_dep_names.add(dep_name)

                if dep_name not in seen:
                    seen.add(dep_name)
                    dep_version = get_latest_version(req.name)
                    if dep_version:
                        next_round.append((dep_name, dep_version))
                        print(f"    -> new build dep: {dep_name}=={dep_version}")

        to_process = next_round

    print(f"\n=== Unique build dep package names ({len(all_build_dep_names)}) ===")
    print("# Paste into requirements-build.in:")
    for dep in sorted(all_build_dep_names):
        print(dep)


if __name__ == "__main__":
    main()
