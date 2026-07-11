#!/usr/bin/env python3
"""Read pinned package versions from pylock.toml for native image builds.

Marker evaluation
-----------------
:func:`evaluate_marker` is **not** a general PEP 508 implementation. It matches
the flat ``(A and B and …) or (C and D) or …`` shape that ``uv`` emits in this
repo's ``pylock.toml`` files today:

* single-quoted literals only (``'…'``) — double quotes are rejected up front
* ``==`` and ``!=`` comparisons on :func:`marker_env` keys, with ``.*`` wildcards
* top-level ``or``, conjunctions joined by ``and`` — no nested ``(A or B) and C``

It does **not** parse arbitrary PEP 508: ``in`` / ``not in``, other comparison
operators, double-quoted strings, or ``and`` / ``or`` *inside* quoted literals
(e.g. ``platform_system == 'Linux and Windows'`` would be split incorrectly).
If ``uv`` changes its marker format, :func:`_assert_marker_format_supported`
should fail loudly with a message to update this script.

Callers format output in shell: ``v${VERSION}`` or ``apache-arrow-${VERSION}`` for git
branches. When the lock carries a local segment (e.g. torch ``2.7.1+cu128``), strip
only the ``+…`` suffix (``${VERSION%%+*}``) before tagging — that removes local
versions but not pre-releases (``1.0a1`` stays ``1.0a1``). Current native-build
pins are plain releases, so this is sufficient today.
"""

from __future__ import annotations

import argparse
import fnmatch
import platform
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

_DEFAULT_PYLOCK = Path("pylock.toml")
_CLAUSE = re.compile(r"^(\w+)\s*(==|!=)\s*'([^']*)'$")
_NON_EQ_COMPARISON = re.compile(r"(?<![=!])(>=|<=|~=)")
_MARKER_FORMAT_HINT = (
    "pylock_version.py only supports uv's current single-quoted, flat (or-of-ands) "
    "marker style — not full PEP 508. If uv changed pylock marker output, update "
    "scripts/pylock_version.py (or use packaging.markers) before merging the lockfile."
)


def _assert_marker_format_supported(marker: str) -> None:
    """Reject marker shapes outside uv's current pylock style before parsing."""
    if '"' in marker:
        raise ValueError(f"unsupported marker uses double-quoted literals: {marker!r}. {_MARKER_FORMAT_HINT}")
    if _NON_EQ_COMPARISON.search(marker):
        raise ValueError(f"unsupported marker comparison operator: {marker!r}. {_MARKER_FORMAT_HINT}")
    if re.search(r"\s+in\s+", marker):
        raise ValueError(f"unsupported marker uses 'in' expression: {marker!r}. {_MARKER_FORMAT_HINT}")
    for branch in _split_outside_parens(marker, " or "):
        inner = _strip_outer_parens(branch)
        if " or " in inner:
            raise ValueError(f"unsupported nested marker disjunction: {marker!r}. {_MARKER_FORMAT_HINT}")
        for clause in _split_outside_parens(inner, " and "):
            if not _CLAUSE.fullmatch(clause.strip()):
                raise ValueError(
                    f"unsupported marker clause {clause.strip()!r} in {marker!r}. "
                    f"Quoted literals must not contain ' and ' / ' or ', and each "
                    f"comparison must use single-quoted values. {_MARKER_FORMAT_HINT}"
                )


def default_pylock_path() -> Path:
    if _DEFAULT_PYLOCK.is_file():
        return _DEFAULT_PYLOCK
    raise FileNotFoundError(f"{_DEFAULT_PYLOCK} not found in {Path.cwd()}")


def python_minor_from_path(pylock_path: Path) -> str:
    match = re.search(r"python-(\d+\.\d+)", pylock_path.as_posix())
    return match.group(1) if match else "3.12"


def marker_env(*, python_minor: str, platform_machine: str) -> dict[str, str]:
    return {
        "python_full_version": f"{python_minor}.0",
        "python_version": python_minor,
        "implementation_name": "cpython",
        "platform_python_implementation": platform.python_implementation(),
        "sys_platform": "linux",
        "platform_machine": platform_machine,
        "platform_system": "Linux",
    }


def _split_outside_parens(marker: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(marker):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and marker.startswith(sep, index):
            parts.append(marker[start:index].strip())
            start = index + len(sep)
    parts.append(marker[start:].strip())
    return parts


def _strip_outer_parens(marker: str) -> str:
    marker = marker.strip()
    while marker.startswith("(") and marker.endswith(")"):
        depth = 0
        for index, char in enumerate(marker):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(marker) - 1:
                    return marker
        marker = marker[1:-1].strip()
    return marker


def _matches_clause(clause: str, env: dict[str, str]) -> bool:
    match = _CLAUSE.fullmatch(clause.strip())
    if not match:
        raise ValueError(f"unsupported marker comparison: {clause!r}. {_MARKER_FORMAT_HINT}")
    key, operator, expected = match.groups()
    if key not in env:
        raise ValueError(f"unsupported marker variable: {key!r}")
    actual = env[key]
    equals = fnmatch.fnmatchcase(actual, expected) if expected.endswith(".*") else actual == expected
    return equals if operator == "==" else not equals


def _branch_matches(branch: str, env: dict[str, str]) -> bool:
    branch = _strip_outer_parens(branch)
    return all(_matches_clause(clause, env) for clause in _split_outside_parens(branch, " and "))


def evaluate_marker(marker: str, env: dict[str, str]) -> bool:
    """Return whether *marker* matches *env* (uv flat or-of-ands style only)."""
    _assert_marker_format_supported(marker)
    return any(_branch_matches(branch, env) for branch in _split_outside_parens(marker, " or "))


def load_pylock_packages(pylock_text: str, *, python_minor: str, platform_machine: str) -> dict[str, dict[str, Any]]:
    doc = tomllib.loads(pylock_text)
    env = marker_env(python_minor=python_minor, platform_machine=platform_machine)
    packages: dict[str, dict[str, Any]] = {}
    for entry in doc.get("packages", []):
        marker = entry.get("marker")
        if marker and not evaluate_marker(marker, env):
            continue
        name = entry["name"]
        if name in packages:
            raise ValueError(f"duplicate package in lockfile: {name}")
        packages[name] = entry
    return packages


def locked_version(
    pylock_path: Path,
    package: str,
    *,
    python_minor: str | None = None,
    platform_machine: str = "x86_64",
) -> str:
    resolved_python = python_minor or python_minor_from_path(pylock_path)
    packages = load_pylock_packages(
        pylock_path.read_text(),
        python_minor=resolved_python,
        platform_machine=platform_machine,
    )
    if package not in packages:
        raise LookupError(
            f"package {package!r} not found in {pylock_path} "
            f"for platform_machine={platform_machine!r} python={resolved_python!r}"
        )
    return packages[package]["version"]


def _parse_args(argv: list[str] | None) -> tuple[Path, str, str | None, str | None]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "positional",
        nargs="+",
        metavar=("PACKAGE", "PYLOCK"),
        help="PACKAGE, or PYLOCK PACKAGE when pylock.toml is not in the cwd",
    )
    parser.add_argument("--platform", help="platform_machine for marker evaluation (default: runtime machine)")
    parser.add_argument("--python", dest="python_minor", help="Python minor version for marker evaluation")
    args = parser.parse_args(argv)

    match len(args.positional):
        case 1:
            pylock_path = default_pylock_path()
            package = args.positional[0]
        case 2:
            pylock_path = Path(args.positional[0])
            package = args.positional[1]
        case _:
            parser.error("expected PACKAGE or PYLOCK PACKAGE")

    return pylock_path, package, args.python_minor, args.platform


def main(argv: list[str] | None = None) -> int:
    try:
        pylock_path, package, python_minor, platform_machine = _parse_args(argv)
        version = locked_version(
            pylock_path,
            package,
            python_minor=python_minor,
            platform_machine=platform_machine or platform.machine(),
        )
    except (FileNotFoundError, LookupError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
