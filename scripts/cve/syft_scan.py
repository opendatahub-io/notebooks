#!/usr/bin/env python3
"""Run syft on the repository and display results with source paths.

Two modes:
  scan   — run syft, show each package with its location (optionally filter by name)
  report — run syft, show a summary grouped by source path

Options:
  --no-config    ignore the repo .syft.yaml (show what syft sees without exclusions)
  --package, -p  filter results to packages matching this substring
  --type, -t     filter results to a specific ecosystem (npm, go-module, python, etc.)
  --json         output raw JSON instead of formatted text

Usage:
    ./uv run scripts/cve/syft_scan.py scan
    ./uv run scripts/cve/syft_scan.py scan -p undici
    ./uv run scripts/cve/syft_scan.py scan --no-config -p undici
    ./uv run scripts/cve/syft_scan.py report
    ./uv run scripts/cve/syft_scan.py report --no-config --type npm
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Location(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str | None = None


class Artifact(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    version: str | None = None
    type: str = "unknown"
    locations: list[Location] = Field(default_factory=list)
    purl: str | None = None


class SyftOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    artifacts: list[Artifact] = Field(default_factory=list)


def find_repo_root() -> Path:
    """Walk up from this script to find the repo root (contains .git)."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    print("Warning: .git not found, falling back to current directory", file=sys.stderr)
    return Path.cwd()


def run_syft(repo_root: Path, *, use_config: bool = True) -> SyftOutput:
    """Run syft scan on the repo root and return parsed output."""
    syft_bin = shutil.which("syft")
    if not syft_bin:
        print("Error: syft not found in PATH. Install from https://github.com/anchore/syft", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()

    extra_args: list[str] = []
    if not use_config:
        config_file = repo_root / ".syft.yaml"
        if config_file.exists():
            empty_config = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", prefix="syft-empty-", delete=False)
            empty_config.write("exclude: []\n")
            empty_config.close()
            extra_args = ["--config", empty_config.name]

    cmd = [
        syft_bin,
        "scan",
        f"dir:{repo_root}",
        "-o",
        "syft-json",
        "-q",
        *extra_args,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env, timeout=600)
    except subprocess.TimeoutExpired:
        print("Error: syft timed out after 600 seconds", file=sys.stderr)
        sys.exit(1)
    finally:
        if not use_config and extra_args:
            Path(extra_args[-1]).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"Error: syft exited with code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(result.stderr[:2000], file=sys.stderr)
        sys.exit(1)

    return SyftOutput.model_validate_json(result.stdout)


def filter_artifacts(
    artifacts: list[Artifact],
    *,
    package: str | None = None,
    pkg_type: str | None = None,
) -> list[Artifact]:
    """Filter artifacts by package name substring and/or ecosystem type."""
    result = artifacts
    if package:
        pkg_lower = package.lower()
        result = [a for a in result if pkg_lower in a.name.lower()]
    if pkg_type:
        type_lower = pkg_type.lower()
        result = [a for a in result if a.type.lower() == type_lower]
    return result


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan mode: list packages with their source locations."""
    repo_root = find_repo_root()
    data = run_syft(repo_root, use_config=not args.no_config)
    artifacts = filter_artifacts(data.artifacts, package=args.package, pkg_type=args.type)

    if args.json:
        print(
            json.dumps(
                [a.model_dump(include={"name", "version", "type", "locations", "purl"}) for a in artifacts], indent=2
            )
        )
        return 0

    artifacts.sort(key=lambda a: (a.locations[0].path or "" if a.locations else "", a.name))

    if not artifacts:
        print("No matching packages found.")
        return 0

    print(f"{'Package':<45} {'Version':<18} {'Type':<16} {'Location'}")
    print("-" * 120)
    for a in artifacts:
        loc = a.locations[0].path or "?" if a.locations else "?"
        ver = a.version or "?"
        dupes = f" (+{len(a.locations) - 1})" if len(a.locations) > 1 else ""
        print(f"{a.name:<45} {ver:<18} {a.type:<16} {loc}{dupes}")

    print(f"\nTotal: {len(artifacts)} package(s)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Report mode: summary grouped by source directory."""
    repo_root = find_repo_root()
    data = run_syft(repo_root, use_config=not args.no_config)
    artifacts = filter_artifacts(data.artifacts, package=args.package, pkg_type=args.type)

    by_type: dict[str, int] = defaultdict(int)
    by_dir: dict[str, list[Artifact]] = defaultdict(list)

    for a in artifacts:
        by_type[a.type] += 1
        dir_keys: set[str] = set()
        for loc_obj in a.locations:
            if not loc_obj.path:
                continue
            loc = loc_obj.path
            parts = loc.strip("/").split("/")
            dir_key = "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:-1]) if len(parts) > 1 else loc
            dir_keys.add(dir_key)

        if not dir_keys:
            dir_keys.add("(no location)")

        for dir_key in dir_keys:
            by_dir[dir_key].append(a)

    if args.json:
        report = {
            "total": len(artifacts),
            "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
            "by_directory": {
                k: {"count": len(v), "packages": [f"{a.name}@{a.version or '?'}" for a in v]}
                for k, v in sorted(by_dir.items(), key=lambda x: -len(x[1]))
            },
        }
        print(json.dumps(report, indent=2))
        return 0

    config_label = "WITHOUT .syft.yaml exclusions" if args.no_config else "with .syft.yaml exclusions"
    print(f"=== Syft Scan Report ({config_label}) ===\n")

    print(f"Total packages found: {len(artifacts)}\n")

    print("By ecosystem:")
    for pkg_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {pkg_type:<20} {count:>5}")

    print(f"\nBy source directory ({len(by_dir)} directories):")
    for dir_key, pkgs in sorted(by_dir.items(), key=lambda x: -len(x[1])):
        types_in_dir: dict[str, int] = defaultdict(int)
        for p in pkgs:
            types_in_dir[p.type] += 1
        type_summary = ", ".join(f"{t}: {c}" for t, c in sorted(types_in_dir.items(), key=lambda x: -x[1]))
        print(f"\n  {dir_key}/ ({len(pkgs)} packages)")
        print(f"    {type_summary}")
        if len(pkgs) <= 10:
            for p in sorted(pkgs, key=lambda x: x.name):
                print(f"      {p.name}@{p.version or '?'}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run syft on the repository and analyze results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore the repo .syft.yaml (run syft without exclusions)",
    )
    common.add_argument(
        "-p",
        "--package",
        help="Filter to packages matching this name substring",
    )
    common.add_argument(
        "-t",
        "--type",
        help="Filter to a specific ecosystem type (npm, go-module, python, etc.)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    subparsers.add_parser(
        "scan",
        parents=[common],
        help="List packages with their source file locations",
    )
    subparsers.add_parser(
        "report",
        parents=[common],
        help="Summary report grouped by directory and ecosystem",
    )

    args = parser.parse_args()

    if args.command == "scan":
        return cmd_scan(args)
    elif args.command == "report":
        return cmd_report(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
