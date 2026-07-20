#!/usr/bin/env python3
"""Extract PEP 517 build-system.requires from sdists on PyPI.

For each pinned package in a requirements.txt, downloads its sdist (if one
exists), reads pyproject.toml, and prints the union of all build deps.

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


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} requirements.txt", file=sys.stderr)
        sys.exit(1)

    reqs_file = sys.argv[1]
    all_build_deps: set[str] = set()

    with open(reqs_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "==" not in line:
                continue
            name_version = line.split(";")[0].strip().split("\\")[0].strip()
            if "==" not in name_version:
                continue
            name, version = name_version.split("==", 1)
            name = name.strip()
            version = version.strip()

            requires = extract_build_requires(name, version)
            if requires:
                print(f"{name}=={version}: {requires}")
                all_build_deps.update(requires)

    print(f"\n# Unique build deps ({len(all_build_deps)})")
    for dep in sorted(all_build_deps, key=str.lower):
        print(f"  {dep}")


if __name__ == "__main__":
    main()
