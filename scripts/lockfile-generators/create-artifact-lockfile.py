#!/usr/bin/env python3
"""create-artifact-lockfile.py — Generate artifacts.lock.yaml from artifacts.in.yaml.

Some build dependencies are not available via package managers (pip, npm, dnf)
and must be fetched as plain files (tarballs, binaries, GPG keys, etc.).
These are listed in artifacts.in.yaml and prefetched by cachi2 as "generic"
type dependencies into cachi2/output/deps/generic/.

This script reads artifacts.in.yaml, downloads each artifact (or uses the
existing cache), computes its SHA-256 checksum, and writes
artifacts.lock.yaml in the same directory.  The lock file is consumed by
cachi2 in Konflux CI; locally, the cached files under
cachi2/output/deps/generic/ are bind-mounted into the build.

Input format (artifacts.in.yaml):
  Each entry can have:
    - url:      (required) The URL to download
    - filename: (optional) Override the filename (default: extracted from URL)
    - checksum: (optional) Expected SHA-256 checksum (validated if present)

Output: artifacts.lock.yaml with download_url, checksum, and filename per artifact.

Usage:
  python3 scripts/lockfile-generators/create-artifact-lockfile.py \\
      --artifact-input path/to/artifacts.in.yaml
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

# Constants
CACHE_BASE_DIR = Path("cachi2/output/deps/generic")
METADATA_VERSION = "1.0"
CHUNK_SIZE = 8192


def get_default_filename(url: str) -> str:
    """Extract filename from URL."""
    return url.rstrip("/").split("/")[-1]


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def download_file(url: str, target_path: Path) -> None:
    """Download URL using wget to target_path."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["wget", "--timeout=60", "--tries=3", "-q", "-O", str(target_path), url]

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise RuntimeError("wget not found: please install wget")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"wget failed for {url}: exit code {e.returncode}")


def normalize_checksum(checksum: str) -> str:
    """Strip sha256: prefix if present; return lowercase hex."""
    return checksum[7:].lower() if checksum.startswith("sha256:") else checksum.lower()


def load_artifact_input(input_path: Path) -> list[Any]:
    """Load and parse the YAML input file."""
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Failed to parse YAML input: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Failed to read {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"Error: Expected a YAML mapping in {input_path}, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)

    items = data.get("input") or []
    if not isinstance(items, list):
        print("Error: 'input' must be a list", file=sys.stderr)
        sys.exit(1)

    return items


def process_artifact(item: dict[str, Any], seen_filenames: set[str]) -> Optional[dict[str, Any]]:
    """Process a single artifact item. Skips duplicate filenames."""
    url = item.get("url")
    if not url:
        print(f"Warning: Skipping item without 'url': {item}", file=sys.stderr)
        return None

    filename = item.get("filename") or get_default_filename(url)
    if filename in seen_filenames:
        print(f"  ⊘ Skipping duplicate filename: {filename}", file=sys.stderr)
        return None
    seen_filenames.add(filename)

    # Guard against path traversal (absolute paths or ".." components)
    cache_file = (CACHE_BASE_DIR / filename).resolve()
    if not cache_file.is_relative_to(CACHE_BASE_DIR.resolve()):
        print(f"Error: filename '{filename}' escapes cache directory — skipping", file=sys.stderr)
        return None

    if cache_file.exists():
        print(f"  ✓ Using existing file: {filename}")
        checksum = compute_sha256(cache_file)
    else:
        print(f"  ↓ Downloading: {url}")
        print(f"    → Saving to: {filename}")
        download_file(url, cache_file)
        checksum = compute_sha256(cache_file)
        print(f"    ✓ Downloaded (sha256: {checksum[:16]}...)")

    provided_checksum = item.get("checksum")
    if provided_checksum:
        expected = normalize_checksum(provided_checksum)
        if checksum.lower() != expected:
            print(f"    ⚠ Warning: Checksum mismatch for {filename}", file=sys.stderr)
            print(f"      Expected: {expected[:16]}...", file=sys.stderr)
            print(f"      Got:      {checksum[:16]}...", file=sys.stderr)

    return {
        "download_url": url,
        "checksum": f"sha256:{checksum}",
        "filename": filename,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate artifacts lockfile.")
    parser.add_argument("--artifact-input", required=True, help="Path to input artifacts.in.yaml")
    args = parser.parse_args()

    input_path = Path(args.artifact_input)
    output_path = input_path.parent / "artifacts.lock.yaml"

    # Create the cache directory if it doesn't exist
    CACHE_BASE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading {input_path}...")
    items = load_artifact_input(input_path)
    print(f"Found {len(items)} artifact(s) to process\n")

    artifacts = []
    seen_filenames: set[str] = set()
    for item in items:
        if isinstance(item, str):
            item = {"url": item}
        elif not isinstance(item, dict):
            print(f"Warning: Skipping invalid item (not a dict or string): {item}", file=sys.stderr)
            continue

        result = process_artifact(item, seen_filenames)
        if result:
            artifacts.append(result)

    if not artifacts:
        print("Error: No artifacts were processed.", file=sys.stderr)
        sys.exit(1)

    # Write lockfile
    lock_data = {
        "metadata": {"version": METADATA_VERSION},
        "artifacts": artifacts,
    }

    class _IndentDumper(yaml.Dumper):
        """YAML dumper that indents sequence items inside mappings."""

        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(
            lock_data, f,
            Dumper=_IndentDumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    print(f"\n✓ Generated {output_path} with {len(artifacts)} artifacts")


if __name__ == "__main__":
    main()
