#!/usr/bin/env python3
"""
Analyze SBOM JSON files for CVE investigation.

This script helps developers find where vulnerable packages are installed
within container images by querying SBOM files from manifest-box.

Supports both:
- Syft native JSON format
- SPDX JSON format (used by manifest-box)

Usage:
    python sbom_analyze.py <sbom.json> <package_name>
    python sbom_analyze.py <sbom.json> --info
    python sbom_analyze.py <sbom.json> --summary

Examples:
    # Find a specific package
    python sbom_analyze.py workbench-sbom.json lodash

    # Get SBOM metadata (source, version, distro)
    python sbom_analyze.py workbench-sbom.json --info

    # Summarize packages by ecosystem type
    python sbom_analyze.py workbench-sbom.json --summary

    # Find all packages at a specific path
    python sbom_analyze.py workbench-sbom.json --path /jupyter/
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def detect_sbom_format(sbom: dict) -> str:
    """Detect whether this is syft native or SPDX format."""
    if "artifacts" in sbom:
        return "syft"
    elif "build_manifest" in sbom and "manifest" in sbom.get("build_manifest", {}):
        return "spdx-manifest-box"
    elif "spdxVersion" in sbom or "packages" in sbom:
        return "spdx"
    else:
        return "unknown"


def extract_purl_type(purl: str) -> str:
    """Extract package type from PURL (e.g., 'pkg:npm/lodash@4.17.21' -> 'npm')."""
    if not purl:
        return "unknown"
    match = re.match(r"pkg:([^/]+)/", purl)
    return match.group(1) if match else "unknown"


def get_components_from_sbom(sbom: dict) -> list[dict]:
    """Get normalized component list from any SBOM format."""
    fmt = detect_sbom_format(sbom)
    
    if fmt == "syft":
        return sbom.get("artifacts", [])
    elif fmt == "spdx-manifest-box":
        # manifest-box wraps SPDX in build_manifest.manifest.components
        return sbom.get("build_manifest", {}).get("manifest", {}).get("components", [])
    elif fmt == "spdx":
        return sbom.get("packages", [])
    else:
        return []


def normalize_component(component: dict, fmt: str) -> dict:
    """Normalize a component to a common format."""
    if fmt == "syft":
        return {
            "name": component.get("name", ""),
            "version": component.get("version"),
            "type": component.get("type", "unknown"),
            "foundBy": component.get("foundBy"),
            "locations": [loc.get("path") for loc in component.get("locations", [])],
            "purl": component.get("purl"),
            "sourceInfo": None,
        }
    elif fmt in ("spdx", "spdx-manifest-box"):
        # Extract PURL from externalRefs
        purl = None
        for ref in component.get("externalRefs", []):
            if ref.get("referenceType") == "purl":
                purl = ref.get("referenceLocator")
                break
        
        pkg_type = extract_purl_type(purl) if purl else "unknown"
        
        # sourceInfo contains the path where the package was found
        source_info = component.get("sourceInfo", "")
        locations = []
        if source_info:
            # Extract path from sourceInfo like "acquired package info from installed node module manifest file: /jupyter/utils/addons/pnpm-lock.yaml"
            if ": " in source_info:
                path = source_info.split(": ", 1)[-1]
                locations = [path]
        
        return {
            "name": component.get("name", ""),
            "version": component.get("versionInfo"),
            "type": pkg_type,
            "foundBy": None,
            "locations": locations,
            "purl": purl,
            "sourceInfo": source_info,
        }
    else:
        return {
            "name": component.get("name", ""),
            "version": None,
            "type": "unknown",
            "foundBy": None,
            "locations": [],
            "purl": None,
            "sourceInfo": None,
        }


def find_package(sbom: dict, package_name: str, case_insensitive: bool = True) -> list[dict]:
    """Find a package in the SBOM and return its details."""
    fmt = detect_sbom_format(sbom)
    components = get_components_from_sbom(sbom)
    
    results = []
    for component in components:
        normalized = normalize_component(component, fmt)
        name = normalized.get("name", "")
        
        if case_insensitive:
            match = package_name.lower() in name.lower()
        else:
            match = package_name == name

        if match:
            results.append(normalized)
    return results


def find_packages_at_path(sbom: dict, path_pattern: str) -> list[dict]:
    """Find all packages installed at a path matching the pattern."""
    fmt = detect_sbom_format(sbom)
    components = get_components_from_sbom(sbom)
    
    results = []
    for component in components:
        normalized = normalize_component(component, fmt)
        locations = normalized.get("locations", [])
        source_info = normalized.get("sourceInfo", "") or ""
        
        # Check both locations and sourceInfo
        matching_locations = [loc for loc in locations if path_pattern in loc]
        source_match = path_pattern in source_info

        if matching_locations or source_match:
            results.append(normalized)
    return results


def get_sbom_info(sbom: dict) -> dict:
    """Extract SBOM metadata (source, version, etc.)."""
    fmt = detect_sbom_format(sbom)
    
    if fmt == "syft":
        return {
            "format": "syft",
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
    elif fmt == "spdx-manifest-box":
        components = get_components_from_sbom(sbom)
        return {
            "format": "spdx (manifest-box)",
            "build_component": sbom.get("build_component"),
            "build_completed_at": sbom.get("build_completed_at"),
            "component_count": len(components),
        }
    elif fmt == "spdx":
        return {
            "format": "spdx",
            "spdx_version": sbom.get("spdxVersion"),
            "name": sbom.get("name"),
            "package_count": len(sbom.get("packages", [])),
        }
    else:
        return {"format": "unknown"}


def summarize_by_type(sbom: dict) -> dict[str, int]:
    """Summarize packages by ecosystem type."""
    fmt = detect_sbom_format(sbom)
    components = get_components_from_sbom(sbom)
    
    counts: dict[str, int] = {}
    for component in components:
        normalized = normalize_component(component, fmt)
        pkg_type = normalized.get("type", "unknown")
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
        if r.get('foundBy'):
            print(f"    Found by: {r['foundBy']}")
        if r.get('locations'):
            print(f"    Locations:")
            for loc in r['locations']:
                print(f"      - {loc}")
        if r.get('sourceInfo'):
            print(f"    Source: {r['sourceInfo']}")
        if r.get('purl'):
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
