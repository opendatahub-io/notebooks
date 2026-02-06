#!/usr/bin/env python3
"""Prefetch pip dependencies from a requirements.txt into cachi2/output/deps/pip/.
1. Get and validate input argument
2. Get list of packages and their checksum
3. Loop: if file doesn't exist, wget
4. Validate each file checksum
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path("cachi2/output/deps/pip")
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"


def get_and_validate_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements", type=Path, help="Path to requirements.txt")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=OUT_DIR, help=f"Output directory (default: {OUT_DIR})",
    )
    args = parser.parse_args()
    req_path = args.requirements.resolve()
    out_dir = args.output_dir.resolve()
    if not req_path.is_file():
        print(f"Error: not a file: {req_path}", file=sys.stderr)
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    return req_path, out_dir


def get_packages_and_checksums(req_path: Path):
    """Parse requirements.txt; yield (name, version, list of sha256 hashes)."""
    text = req_path.read_text()
    text = re.sub(r" \\\n\s*", " ", text)
    lines = text.split("\n")
    block = None
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("--index-url ") or s.startswith("--extra-index-url "):
            continue
        if "==" in s and not line.startswith((" ", "\t")):
            if block:
                yield block
            block = [s]
        elif block is not None and "--hash=" in s:
            block.append(s)
    if block:
        yield block


def block_to_name_version_hashes(block):
    """(name, version, [sha256, ...])."""
    first = block[0].split("--hash=")[0].strip().rstrip(";").strip()
    # "name==version" or "name==version ; markers"
    name_ver = first.split(";")[0].strip()
    if "==" not in name_ver:
        return None, None, []
    name, version = name_ver.split("==", 1)
    hashes = []
    for line in block:
        hashes.extend(re.findall(r"--hash=sha256:([a-f0-9]+)", line, re.I))
    return name, version, list(dict.fromkeys(hashes))


def fetch_pypi_urls(name: str, version: str, wanted_hashes: set):
    """Return list of (url, filename, sha256) for urls whose sha256 is in wanted_hashes."""
    url = PYPI_JSON.format(name=name, version=version)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return []
    
    out = []
    for entry in data.get("urls", []):
        filename = entry["url"].split("/")[-1].split("?")[0]
        
        # --- NEW FILTER LOGIC ---
        # 1. Skip Windows, MacOS, iOS
        if any(x in filename for x in ["macosx", "win_amd64", "win32", "win_arm64", "ios_"]):
            continue
        
        # 2. Skip Python versions other than 3.12 (unless it's 'py3-none-any')
        # if "-cp" in filename and "cp312" not in filename:
        #     continue
        # ------------------------

        digests = entry.get("digests") or {}
        h = digests.get("sha256")
        if h and h in wanted_hashes:
            u = entry["url"]
            out.append((u, filename, h))
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wget(url: str, path: Path):
    subprocess.run(["wget", "-q", "-O", str(path), url], check=True)


def main():
    req_path, out_dir = get_and_validate_args()

    # Build list of (path, expected_sha256, url, name, version, filename) per file to have
    to_fetch = []
    for block in get_packages_and_checksums(req_path):
        name, version, hashes = block_to_name_version_hashes(block)
        if not name or not version or not hashes:
            continue
        for url, filename, expected_hash in fetch_pypi_urls(name, version, set(hashes)):
            to_fetch.append((out_dir / filename, expected_hash, url, name, version, filename))

    total = len(to_fetch)
    for idx, (path, expected_hash, url, name, version, filename) in enumerate(to_fetch, 1):
        print(f"[{idx}/{total}] {name}=={version}  {filename}")
        if not path.exists():
            print(f"  Downloading: {url}")
            wget(url, path)
        else:
            print(f"  Already exists, skipping download.")
        actual = file_sha256(path)
        if actual != expected_hash:
            print(f"Error: {path.name} checksum mismatch (got {actual}, expected {expected_hash})", file=sys.stderr)
            sys.exit(1)
        print(f"  Checksum OK (sha256:{actual[:16]}...)")
    print(f"Done: {total} file(s) present and validated.")


if __name__ == "__main__":
    main()
