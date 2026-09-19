#!/usr/bin/env python3
"""Extract the pinned @playwright/test version from package.json5.

package.json5 is the single source of truth; container tags are v{version}-noble.

Usage: scripts/get_playwright_version.py [path/to/package.json5]
Default: tests/browser/package.json5
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pyjson5

# Matches version values such as: '=1.61.1'
_VERSION_RE = re.compile(r"=?([0-9]+\.[0-9]+\.[0-9]+)")
_DEFAULT_MANIFEST = Path("tests/browser/package.json5")


def extract_playwright_version(manifest: Path) -> str:
    package = pyjson5.loads(manifest.read_text(encoding="utf-8"))
    dependencies = package.get("devDependencies", {})
    version = dependencies.get("@playwright/test") if isinstance(dependencies, dict) else None
    match = _VERSION_RE.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise ValueError(f"Failed to extract valid @playwright/test version from {manifest}")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=_DEFAULT_MANIFEST,
        help=f"path to package.json5 (default: {_DEFAULT_MANIFEST})",
    )
    args = parser.parse_args(argv)

    try:
        print(extract_playwright_version(args.manifest))
    except (OSError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
