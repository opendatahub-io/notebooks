#!/usr/bin/env python3
"""
Analyze syft SBOM JSON files for CVE investigation.

This script helps developers find where vulnerable packages are installed
within container images by querying SBOM files from manifest-box.

Usage:
    python sbom_analyze.py <sbom.json> <package_name>
    python sbom_analyze.py <sbom.json> --info
    python sbom_analyze.py <sbom.json> --summary

Examples:
    # Find a specific package
    python sbom_analyze.py codeserver-sbom.json esbuild

    # Get SBOM metadata (source, version, distro)
    python sbom_analyze.py codeserver-sbom.json --info

    # Summarize packages by ecosystem type
    python sbom_analyze.py codeserver-sbom.json --summary

    # Find all packages at a specific path
    python sbom_analyze.py codeserver-sbom.json --path /code-server/
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def find_package(sbom: dict, package_name: str, case_insensitive: bool = True) -> list[dict]:
    """Find a package in the SBOM and return its details."""
    results = []
    for artifact in sbom.get("artifacts", []):
        name = artifact.get("name", "")
        if case_insensitive:
            match = package_name.lower() in name.lower()
        else:
            match = package_name == name

        if match:
            results.append({
                "name": name,
                "version": artifact.get("version"),
                "type": artifact.get("type"),
                "foundBy": artifact.get("foundBy"),
                "locations": [loc.get("path") for loc in artifact.get("locations", [])],
                "purl": artifact.get("purl"),
            })
    return results


def find_packages_at_path(sbom: dict, path_pattern: str) -> list[dict]:
    """Find all packages installed at a path matching the pattern."""
    results = []
    for artifact in sbom.get("artifacts", []):
        locations = [loc.get("path", "") for loc in artifact.get("locations", [])]
        matching_locations = [loc for loc in locations if path_pattern in loc]

        if matching_locations:
            results.append({
                "name": artifact.get("name"),
                "version": artifact.get("version"),
                "type": artifact.get("type"),
                "locations": matching_locations,
            })
    return results


def get_sbom_info(sbom: dict) -> dict:
    """Extract SBOM metadata (source, version, etc.)."""
    return {
        "source_name": sbom.get("source", {}).get("name"),
        "source_version": sbom.get("source", {}).get("version"),
        "source_type": sbom.get("source", {}).get("type"),
        "distro": sbom.get("distro", {}).get("name"),
        "distro_version": sbom.get("distro", {}).get("version"),
        "syft_version": sbom.get("descriptor", {}).get("version"),
        "schema_version": sbom.get("schema", {}).get("version"),
        "artifact_count": len(sbom.get("artifacts", [])),
        "file_count": len(sbom.get("files", [])),
    }


def summarize_by_type(sbom: dict) -> dict[str, int]:
    """Summarize packages by ecosystem type."""
    counts: dict[str, int] = {}
    for artifact in sbom.get("artifacts", []):
        pkg_type = artifact.get("type", "unknown")
        counts[pkg_type] = counts.get(pkg_type, 0) + 1

    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def load_sbom(sbom_path: str) -> dict:
    """Load and parse SBOM JSON file."""
    with open(sbom_path) as f:
        return json.load(f)


def print_package_results(results: list[dict], package_name: str) -> None:
    """Pretty-print package search results."""
    if not results:
        print(f"  Package '{package_name}' not found")
        return

    print(f"  Found {len(results)} matching package(s):\n")
    for r in results:
        print(f"  {r['name']}@{r['version']}")
        print(f"    Type: {r['type']}")
        print(f"    Found by: {r['foundBy']}")
        print(f"    Locations:")
        for loc in r['locations']:
            print(f"      - {loc}")
        if r['purl']:
            print(f"    PURL: {r['purl']}")
        print()


def print_path_results(results: list[dict], path_pattern: str) -> None:
    """Pretty-print path search results."""
    if not results:
        print(f"  No packages found at path matching '{path_pattern}'")
        return

    print(f"  Found {len(results)} package(s) at path matching '{path_pattern}':\n")
    for r in results:
        print(f"  {r['name']}@{r['version']} ({r['type']})")
        for loc in r['locations']:
            print(f"    - {loc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze syft SBOM JSON files for CVE investigation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s sbom.json esbuild          # Find package by name
  %(prog)s sbom.json --info           # Show SBOM metadata
  %(prog)s sbom.json --summary        # Show package count by type
  %(prog)s sbom.json --path /opt/     # Find packages at path

Location patterns help determine remediation:
  /lib/apk/db/installed                → Alpine system package
  /var/lib/dpkg/status                 → Debian/Ubuntu package
  /usr/lib/python*/site-packages/      → Python package
  */node_modules/*/package.json        → npm package
  /usr/share/gems/                     → Ruby gem
        """,
    )
    parser.add_argument("sbom_file", help="Path to SBOM JSON file")
    parser.add_argument("package_name", nargs="?", help="Package name to search for")
    parser.add_argument("--info", action="store_true", help="Show SBOM metadata")
    parser.add_argument("--summary", action="store_true", help="Summarize packages by type")
    parser.add_argument("--path", help="Find packages at a specific path")
    parser.add_argument("--exact", action="store_true", help="Exact package name match")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    # Validate arguments
    if not args.info and not args.summary and not args.path and not args.package_name:
        parser.error("Must specify package_name, --info, --summary, or --path")

    # Load SBOM
    try:
        sbom = load_sbom(args.sbom_file)
    except FileNotFoundError:
        print(f"Error: File not found: {args.sbom_file}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.sbom_file}: {e}", file=sys.stderr)
        return 1

    # Process commands
    if args.info:
        print("=== SBOM Info ===")
        info = get_sbom_info(sbom)
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            for k, v in info.items():
                print(f"  {k}: {v}")

    if args.summary:
        print("\n=== Package Summary by Type ===")
        summary = summarize_by_type(sbom)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            for pkg_type, count in summary.items():
                print(f"  {pkg_type}: {count}")

    if args.path:
        print(f"\n=== Packages at path matching '{args.path}' ===")
        results = find_packages_at_path(sbom, args.path)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_path_results(results, args.path)

    if args.package_name:
        print(f"\n=== Searching for '{args.package_name}' ===")
        results = find_package(sbom, args.package_name, case_insensitive=not args.exact)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_package_results(results, args.package_name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
