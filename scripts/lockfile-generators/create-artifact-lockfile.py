#!/usr/bin/env python3
"""
Generate artifacts.lock.yaml from artifacts.in.yaml

Reads a list of URLs from the input YAML file. Each entry can have:
- url: (required) The URL to download
- filename: (optional) The path/filename to save the file as
- checksum: (optional) Expected SHA256 checksum

Files are saved to: cachi2/output/deps/generic/{filename}
If filename is not provided, it's extracted from the URL.

Usage: python create-artifact-lockfile.py --artifact-input=path/to/artifacts.in.yaml
"""
import hashlib
import sys
import subprocess
import argparse
from pathlib import Path
import yaml

# Constants
CACHE_BASE_DIR = Path("cachi2/output/deps/generic")
METADATA_VERSION = "1.0"


def get_default_filename(url: str) -> str:
    """Extract filename from URL."""
    return url.rstrip("/").split("/")[-1]


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
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


def load_artifact_input(input_path: Path) -> list:
    """Load and parse the YAML input file."""
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to parse YAML input: {e}", file=sys.stderr)
        sys.exit(1)

    # Get the input list
    items = data.get("input") or []
    if not isinstance(items, list):
        print(f"Error: 'input' must be a list", file=sys.stderr)
        sys.exit(1)

    return items


def process_artifact(item: dict) -> dict:
    """Process a single artifact item."""
    url = item.get("url")
    if not url:
        print(f"Warning: Skipping item without 'url': {item}", file=sys.stderr)
        return None

    # Determine filename
    filename = item.get("filename")
    if not filename:
        filename = get_default_filename(url)

    # Build full cache path
    cache_file = CACHE_BASE_DIR / filename

    # Check if file already exists
    if cache_file.exists():
        print(f"  ✓ Using existing file: {filename}")
        checksum = compute_sha256(cache_file)
    else:
        # Download the file
        print(f"  ↓ Downloading: {url}")
        print(f"    → Saving to: {filename}")
        download_file(url, cache_file)
        checksum = compute_sha256(cache_file)
        print(f"    ✓ Downloaded (sha256: {checksum[:16]}...)")

    # Handle provided checksum (validate if given)
    provided_checksum = item.get("checksum")
    if provided_checksum:
        # Normalize checksum format
        if provided_checksum.startswith("sha256:"):
            expected_checksum = provided_checksum[7:]  # Remove "sha256:" prefix
        else:
            expected_checksum = provided_checksum

        if checksum != expected_checksum:
            print(f"    ⚠ Warning: Checksum mismatch for {filename}", file=sys.stderr)
            print(f"      Expected: {expected_checksum[:16]}...", file=sys.stderr)
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
    for item in items:
        # Handle case where item might be a string (just a URL)
        if isinstance(item, str):
            item = {"url": item}
        elif not isinstance(item, dict):
            print(f"Warning: Skipping invalid item (not a dict or string): {item}", file=sys.stderr)
            continue

        result = process_artifact(item)
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

    with open(output_path, "w") as f:
        yaml.dump(lock_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\n✓ Generated {output_path} with {len(artifacts)} artifacts")


if __name__ == "__main__":
    main()
