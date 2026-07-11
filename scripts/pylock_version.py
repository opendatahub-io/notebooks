#!/usr/bin/env python3
"""Read pinned package versions from pylock.toml for native image builds.

Marker support is intentionally narrow: ``or`` / ``and`` groups of ``==`` and
``!=`` comparisons on the env keys built by :func:`marker_env`, with ``.*``
wildcards for python version pins. Anything else raises :class:`ValueError`.
"""

from __future__ import annotations

import argparse
import fnmatch
import platform
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Literal

VersionFormat = Literal["pep440", "git-tag", "apache-arrow-branch"]
_DEFAULT_PYLOCK = Path("pylock.toml")
_CLAUSE = re.compile(r"^(\w+)\s*(==|!=)\s*'([^']*)'$")
_BASE_VERSION = re.compile(r"^(\d+(?:\.\d+)*)")


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
        raise ValueError(f"unsupported marker comparison: {clause!r}")
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
    return any(_branch_matches(branch, env) for branch in _split_outside_parens(marker, " or "))


def base_version(version: str) -> str:
    public = version.split("!", 1)[-1].split("+", 1)[0]
    match = _BASE_VERSION.match(public)
    if not match:
        raise ValueError(f"cannot derive base version from {version!r}")
    return match.group(1)


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


def format_version(version: str, fmt: VersionFormat) -> str:
    match fmt:
        case "pep440":
            return version
        case "git-tag":
            return f"v{base_version(version)}"
        case "apache-arrow-branch":
            return f"apache-arrow-{base_version(version)}"
        case _:
            raise ValueError(f"unsupported format: {fmt}")


def _parse_args(argv: list[str] | None) -> tuple[Path, str, str | None, str | None, VersionFormat]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "positional",
        nargs="+",
        metavar=("PACKAGE", "PYLOCK"),
        help="PACKAGE, or PYLOCK PACKAGE when pylock.toml is not in the cwd",
    )
    parser.add_argument("--platform", help="platform_machine for marker evaluation (default: runtime machine)")
    parser.add_argument("--python", dest="python_minor", help="Python minor version for marker evaluation")
    parser.add_argument(
        "--format",
        choices=("apache-arrow-branch", "git-tag", "pep440"),
        default="pep440",
        help="output format (default: pep440)",
    )
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

    return pylock_path, package, args.python_minor, args.platform, args.format


def main(argv: list[str] | None = None) -> int:
    try:
        pylock_path, package, python_minor, platform_machine, fmt = _parse_args(argv)
        version = locked_version(
            pylock_path,
            package,
            python_minor=python_minor,
            platform_machine=platform_machine or platform.machine(),
        )
    except (FileNotFoundError, LookupError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(format_version(version, fmt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
