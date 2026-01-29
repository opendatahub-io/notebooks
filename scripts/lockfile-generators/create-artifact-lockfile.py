#!/usr/bin/env python3
import hashlib
import sys
import subprocess
import argparse
from pathlib import Path
import yaml

"""
Generate artifacts.lock.yaml from artifacts.in.yaml

Reads artifact groups from a YAML input file (default: artifacts.in.yaml).
Each group may provide a `directory` and a `urls` list. Each url entry can
be either a mapping with `url` and optional `filename` and `checksum`, or a
short form mapping with just `url`.

If a checksum is present in the input it is used as-is. Otherwise the script
downloads the file into the cache directory under its provided `directory`
and computes the sha256 checksum. The output `artifacts.lock.yaml` lists
entries with `download_url`, `checksum` and `filename` (filename includes the
directory prefix when provided).

Usage: python create-artifact-lockfile.py --artifact-input=path/to/artifacts.in.yaml
"""

# --- Constants ---
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

def download_and_hash(url: str, target_path: Path) -> str:
    """Download URL using wget and return sha256 hex digest."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["wget", "--timeout=60", "--tries=3", "-q", "-O", str(target_path), url]

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise RuntimeError("wget not found: please install wget")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"wget failed for {url}: exit code {e.returncode}")

    checksum = compute_sha256(target_path)
    print(f"  ✓ Downloaded {target_path} (sha256: {checksum[:16]}...)")
    return checksum

def load_artifact_input(input_path: Path) -> list:
    """Reads and pre-processes the YAML input into a list of groups."""
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    raw_text = input_path.read_text()
    # Pre-process YAML to handle repeated 'directory:' keys
    cleaned = raw_text.replace("input:\n    directory:", "input:\n  - directory:")
    cleaned = cleaned.replace("\n\n    directory:", "\n\n  - directory:")

    try:
        data = yaml.safe_load(cleaned)
    except Exception as e:
        print(f"Failed to parse YAML input: {e}", file=sys.stderr)
        sys.exit(1)

    groups = data.get("input") or []
    return [groups] if isinstance(groups, dict) else groups

def resolve_artifact(item: dict, directory: str, seen: set) -> dict:
    """Logic to resolve a single artifact's filename and checksum."""
    url = item.get("url")
    base_name = item.get("filename") or get_default_filename(url)
    filename = str(Path(directory) / base_name) if directory else base_name

    if filename in seen:
        return None
    seen.add(filename)

    cache_file = CACHE_BASE_DIR / filename
    provided_checksum = item.get("checksum")

    if provided_checksum:
        checksum_full = provided_checksum if provided_checksum.startswith("sha256:") else f"sha256:{provided_checksum}"
    else:
        try:
            checksum = compute_sha256(cache_file) if cache_file.exists() else download_and_hash(url, cache_file)
            checksum_full = f"sha256:{checksum}"
        except Exception as e:
            print(f"  error: {url}: {e}", file=sys.stderr)
            return None

    return {
        "download_url": url,
        "checksum": checksum_full,
        "filename": filename,
    }

def process_groups(groups: list) -> list:
    """Iterate through groups and items to build the artifact list."""
    artifacts = []
    seen_filenames = set()

    for group in groups:
        directory = (group.get("directory") or "").strip()
        urls = group.get("urls") or []
        
        for item in urls:
            resolved = resolve_artifact(item, directory, seen_filenames)
            if resolved:
                artifacts.append(resolved)
    return artifacts

def write_lockfile(output_path: Path, artifacts: list) -> None:
    """Constructs the lockfile structure and writes to disk."""
    lock_data = {
        "metadata": {"version": METADATA_VERSION},
        "artifacts": artifacts,
    }
    
    with open(output_path, "w") as f:
        yaml.dump(lock_data, f, default_flow_style=False, sort_keys=False)
    
    print(f"✓ Generated {output_path} with {len(artifacts)} artifacts")

def main():
    parser = argparse.ArgumentParser(description="Generate artifacts lockfile.")
    parser.add_argument("--artifact-input", required=True, help="Path to input artifacts.in.yaml")
    args = parser.parse_args()
    
    input_path = Path(args.artifact_input)
    output_path = input_path.parent / "artifacts.lock.yaml"

    # Create the directory (including parents) if it doesn't exist
    CACHE_BASE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading {input_path}...")
    groups = load_artifact_input(input_path)
    artifacts = process_groups(groups)
    
    write_lockfile(output_path, artifacts)

if __name__ == "__main__":
    main()