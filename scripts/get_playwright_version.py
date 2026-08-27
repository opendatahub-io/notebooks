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

# Matches package.json5 pins such as: '@playwright/test': '=1.61.1',
_VERSION_RE = re.compile(
    r"""
    ['"]@playwright/test['"]  # dependency key (single- or double-quoted)
    \s*:\s*                   # JSON5 key/value separator
    ['"]                      # opening quote of the version string
    =?                        # optional exact-pin prefix used in this repo (=1.61.1)
    (                         # capture group: semver x.y.z
        [0-9]+ \. [0-9]+ \. [0-9]+
    )
    ['"]                      # closing quote
    """,
    re.VERBOSE,
)
_DEFAULT_MANIFEST = Path("tests/browser/package.json5")


def strip_json5_comments(text: str) -> str:
    """Strip single-line (//) and multi-line (/* ... */) comments from JSON5 text."""
    # Remove block comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove line comments
    text = re.sub(r'//.*', '', text)
    return text


def extract_playwright_version(manifest: Path) -> str:
    text = manifest.read_text(encoding="utf-8")
    cleaned_text = strip_json5_comments(text)
    matches = _VERSION_RE.findall(cleaned_text)
    if not matches:
        raise ValueError(f"Failed to extract valid @playwright/test version from {manifest}")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous @playwright/test versions found in {manifest}: {matches}")
    return matches[0]


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
