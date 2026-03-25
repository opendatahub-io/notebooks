#!/usr/bin/env python3
"""
Fetch a single manifest-box SBOM JSON via GitLab API + Git LFS.

This helper is for one-off CVE triage where downloading the full SQLite database
or cloning the entire manifest-box repo would be excessive.

Examples:
    # List matching SBOM files for a component substring
    python scripts/cve/fetch_manifestbox_sbom.py --component odh-workbench-codeserver-datascience-cpu-py312-rhel9 --list-only

    # Download the second matching SBOM and inspect a package
    python scripts/cve/fetch_manifestbox_sbom.py \
        --component odh-workbench-codeserver-datascience-cpu-py312-rhel9 \
        --pick 2 \
        --output .artifacts/sbom/codeserver-v3-3.json \
        --package undici
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


TREE_URL = (
    "https://gitlab.cee.redhat.com/api/v4/projects/"
    "product-security%2Fmanifest-box/repository/tree"
    "?path=manifests/konflux/openshift-ai&per_page=1000"
)
FILE_RAW_TEMPLATE = (
    "https://gitlab.cee.redhat.com/api/v4/projects/"
    "product-security%2Fmanifest-box/repository/files/{encoded_path}/raw?ref=main"
)
LFS_BATCH_URL = (
    "https://gitlab.cee.redhat.com/product-security/manifest-box.git/info/lfs/objects/batch"
)


def run_curl(
    args: list[str], data: str | None = None, insecure: bool = False
) -> subprocess.CompletedProcess[str]:
    curl_args = ["curl", "-fsSL"]
    if insecure:
        curl_args.append("-k")
    return subprocess.run(
        [*curl_args, *args],
        input=data,
        text=True,
        capture_output=True,
        check=True,
    )


def fetch_tree(insecure: bool = False) -> list[dict]:
    result = run_curl([TREE_URL], insecure=insecure)
    return json.loads(result.stdout)


def find_matches(component: str, entries: list[dict]) -> list[dict]:
    needle = component.lower()
    matches = [
        entry
        for entry in entries
        if needle in entry.get("name", "").lower() or needle in entry.get("path", "").lower()
    ]
    return sorted(matches, key=lambda entry: entry["name"])


def print_matches(matches: list[dict]) -> None:
    if not matches:
        print("No manifest-box SBOM files matched.")
        return

    print("Matching manifest-box SBOM files:")
    for index, match in enumerate(matches, start=1):
        print(f"{index}. {match['name']}")


def fetch_file_pointer(path: str, insecure: bool = False) -> str:
    encoded_path = quote(path, safe="")
    url = FILE_RAW_TEMPLATE.format(encoded_path=encoded_path)
    return run_curl([url], insecure=insecure).stdout


def parse_lfs_pointer(pointer_text: str) -> tuple[str, int] | None:
    stripped = pointer_text.lstrip()
    if stripped.startswith("{"):
        return None

    oid_match = re.search(r"^oid sha256:([0-9a-f]+)$", pointer_text, re.MULTILINE)
    size_match = re.search(r"^size ([0-9]+)$", pointer_text, re.MULTILINE)
    if not oid_match or not size_match:
        raise ValueError("Could not parse Git LFS pointer")

    return oid_match.group(1), int(size_match.group(1))


def request_lfs_download_url(oid: str, size: int, insecure: bool = False) -> str:
    payload = {
        "operation": "download",
        "transfers": ["basic"],
        "objects": [{"oid": oid, "size": size}],
    }
    result = run_curl(
        [
            "-X",
            "POST",
            LFS_BATCH_URL,
            "-H",
            "Accept: application/vnd.git-lfs+json",
            "-H",
            "Content-Type: application/vnd.git-lfs+json",
            "-d",
            json.dumps(payload),
        ],
        insecure=insecure,
    )
    data = json.loads(result.stdout)
    return data["objects"][0]["actions"]["download"]["href"]


def download_to_file(url: str, output_path: Path, insecure: bool = False) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    curl_args = ["curl", "-fsSL"]
    if insecure:
        curl_args.append("-k")
    subprocess.run([*curl_args, url, "-o", str(output_path)], check=True)


def write_text(output_path: Path, content: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)


def default_output_path(component: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", component).strip("_")
    return Path(".artifacts/sbom") / f"{safe_name}.json"


def print_sbom_metadata(output_path: Path) -> None:
    with output_path.open() as handle:
        data = json.load(handle)

    print(f"Downloaded: {output_path}")
    build_component = data.get("build_component")
    if build_component:
        print(f"build_component: {build_component}")
    completed_at = data.get("build_completed_at")
    if completed_at:
        print(f"build_completed_at: {completed_at}")


def run_package_lookup(output_path: Path, package: str) -> None:
    print()
    subprocess.run(
        [sys.executable, "scripts/cve/sbom_analyze.py", str(output_path), package],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch one manifest-box SBOM JSON via GitLab API + Git LFS."
    )
    parser.add_argument("--component", required=True, help="Component/image substring to search for")
    parser.add_argument(
        "--pick",
        type=int,
        help="1-based match index to download when multiple SBOM files match",
    )
    parser.add_argument(
        "--output",
        help="Output file path (defaults to .artifacts/sbom/<component>.json)",
    )
    parser.add_argument(
        "--package",
        help="Optional package name to inspect immediately after download",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list matching SBOM filenames without downloading",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Pass -k to curl for internal cert environments that lack the CA chain",
    )

    args = parser.parse_args()

    try:
        entries = fetch_tree(insecure=args.insecure)
    except subprocess.CalledProcessError as exc:
        print(f"Error querying manifest-box tree: {exc.stderr}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error parsing manifest-box tree response: {exc}", file=sys.stderr)
        return 1

    matches = find_matches(args.component, entries)
    if not matches:
        print(f"No SBOM files matched component substring: {args.component}", file=sys.stderr)
        return 1

    if args.list_only:
        print_matches(matches)
        return 0

    if len(matches) > 1 and args.pick is None:
        print_matches(matches)
        print("\nMultiple matches found; re-run with --pick N.", file=sys.stderr)
        return 2

    selected_index = (args.pick or 1) - 1
    if selected_index < 0 or selected_index >= len(matches):
        print(f"Invalid --pick value: {args.pick}", file=sys.stderr)
        return 1

    selected = matches[selected_index]
    output_path = Path(args.output) if args.output else default_output_path(args.component)

    try:
        pointer_text = fetch_file_pointer(selected["path"], insecure=args.insecure)
        lfs_info = parse_lfs_pointer(pointer_text)
        if lfs_info is None:
            write_text(output_path, pointer_text)
        else:
            oid, size = lfs_info
            download_url = request_lfs_download_url(oid, size, insecure=args.insecure)
            download_to_file(download_url, output_path, insecure=args.insecure)
    except (subprocess.CalledProcessError, ValueError, KeyError, IndexError) as exc:
        print(f"Error downloading SBOM for {selected['name']}: {exc}", file=sys.stderr)
        return 1

    try:
        print_sbom_metadata(output_path)
    except json.JSONDecodeError as exc:
        print(f"Downloaded file is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if args.package:
        try:
            run_package_lookup(output_path, args.package)
        except subprocess.CalledProcessError as exc:
            print(f"Package lookup failed: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
