#!/usr/bin/env python3
"""download-pip-packages.py — Prefetch pip wheels/sdists for offline builds.

Downloads all packages listed in a requirements.txt (with --hash=sha256:…
lines) into cachi2/output/deps/pip/.  This is the local-development equivalent
of what cachi2 does automatically in Konflux CI — it populates the same
directory so that `podman build` can install
packages with --no-index --find-links /cachi2/output/deps/pip.

Supports two index backends:
  • PyPI (default) — uses the JSON API (https://pypi.org/pypi/{name}/{ver}/json)
    to resolve download URLs for each hash.
  • PEP 503 simple indexes — auto-detected when the requirements file contains
    an --index-url that is not pypi.org (e.g. the RHOAI index).  Parses the
    simple HTML page to match hashes to download URLs.

Steps:
  1. Parse the requirements file for (name, version, sha256 hashes).
  2. Detect --index-url (if present) to choose PyPI JSON vs. simple index.
  3. For each package, resolve download URLs that match the requested hashes.
  4. Skip files that already exist locally; download missing ones with wget.
  5. Verify every file's sha256 checksum (whether freshly downloaded or cached).

Usage:
  python3 scripts/lockfile-generators/download-pip-packages.py \
      [-o OUTPUT_DIR] [--arch ARCH] <requirements.txt>

Can be invoked standalone or by create-requirements-lockfile.sh (which has
its own inline download step for pylock.toml-based workflows).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
import os
import concurrent.futures
from pathlib import Path

OUT_DIR = Path(os.environ.get("CACHI2_OUT_DIR", "cachi2/output")) / "deps" / "pip"
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"


def get_and_validate_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements", type=Path, help="Path to requirements.txt")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=OUT_DIR, help=f"Output directory (default: {OUT_DIR})",
    )
    parser.add_argument(
        "--arch", type=str, default=os.environ.get("ARCH", "amd64"), help="Target architecture (e.g. amd64, arm64)"
    )
    args = parser.parse_args()
    req_path = args.requirements.resolve()
    out_dir = args.output_dir.resolve()
    if not req_path.is_file():
        print(f"Error: not a file: {req_path}", file=sys.stderr)
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    return req_path, out_dir, args.arch


def detect_index_url(req_path: Path):
    """Return the --index-url value from the requirements file, or None."""
    for line in req_path.read_text().splitlines():
        m = re.match(r"^\s*--index-url\s+(\S+)", line)
        if m:
            return m.group(1)
    return None


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
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return []
    
    out = []
    for entry in data.get("urls", []):
        filename = entry["url"].split("/")[-1].split("?")[0]
        
        # Skip Windows, MacOS, iOS
        if any(x in filename for x in ["macosx", "win_amd64", "win32", "win_arm64", "ios_"]):
            continue

        digests = entry.get("digests") or {}
        h = digests.get("sha256")
        if h and h in wanted_hashes:
            u = entry["url"]
            out.append((u, filename, h))
    return out


def fetch_simple_index_urls(index_url: str, name: str, version: str, wanted_hashes: set):
    """Return list of (url, filename, sha256) from a PEP 503 simple index page."""
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    page_url = f"{index_url.rstrip('/')}/{normalized}/"
    try:
        req = urllib.request.Request(page_url, headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode()
    except Exception as e:
        print(f"Error fetching {page_url}: {e}", file=sys.stderr)
        return []

    out = []
    for m in re.finditer(r'<a\s+href="([^"]*?)#sha256=([a-f0-9]+)"[^>]*>([^<]+)</a>', html):
        download_url, sha, filename = m.group(1), m.group(2), m.group(3).strip()
        if sha in wanted_hashes:
            out.append((download_url, filename, sha))
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wget(url: str, path: Path):
    subprocess.run(["wget", "-q", "-O", str(path), url], check=True)


def download_and_verify(item):
    path, expected_hash, url, name, version, filename = item
    if not path.exists():
        print(f"  Downloading: {filename}")
        try:
            wget(url, path)
        except subprocess.CalledProcessError as e:
            return False, f"Error downloading {filename}: {e}"
    
    actual = file_sha256(path)
    if actual != expected_hash:
        return False, f"{filename} checksum mismatch (got {actual}, expected {expected_hash})"
    return True, f"{filename} OK"


def should_keep_for_arch(filename: str, arch: str) -> bool:
    if "any" in filename or "noarch" in filename:
        return True
        
    arch_tags = []
    if arch in ["amd64", "x86_64"]:
        arch_tags = ["x86_64", "amd64"]
    elif arch in ["arm64", "aarch64"]:
        arch_tags = ["aarch64", "arm64"]
    elif arch == "ppc64le":
        arch_tags = ["ppc64le"]
    elif arch == "s390x":
        arch_tags = ["s390x"]
        
    all_arches = ["x86_64", "amd64", "aarch64", "arm64", "ppc64le", "s390x"]
    has_arch = False
    for a in all_arches:
        if a in filename:
            has_arch = True
            break
            
    if not has_arch:
        return True
        
    for a in arch_tags:
        if a in filename:
            return True
    return False


def main():
    req_path, out_dir, arch = get_and_validate_args()

    index_url = detect_index_url(req_path)
    use_simple_index = index_url is not None and "pypi.org" not in index_url
    if use_simple_index:
        print(f"Detected custom index: {index_url}")
        print(f"Using PEP 503 simple index for downloads.\n")

    to_fetch = []
    for block in get_packages_and_checksums(req_path):
        name, version, hashes = block_to_name_version_hashes(block)
        if not name or not version or not hashes:
            continue

        if use_simple_index:
            results = fetch_simple_index_urls(index_url, name, version, set(hashes))
        else:
            results = fetch_pypi_urls(name, version, set(hashes))

        for url, filename, expected_hash in results:
            if should_keep_for_arch(filename, arch):
                to_fetch.append((out_dir / filename, expected_hash, url, name, version, filename))

    total = len(to_fetch)
    print(f"Found {total} wheels to fetch for arch {arch}.")
    
    success = True
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_and_verify, item): item for item in to_fetch}
        for future in concurrent.futures.as_completed(futures):
            ok, msg = future.result()
            if not ok:
                print(f"Error: {msg}", file=sys.stderr)
                success = False
            else:
                print(f"  {msg}")

    if not success:
        sys.exit(1)
    print(f"Done: {total} file(s) present and validated.")


if __name__ == "__main__":
    main()
