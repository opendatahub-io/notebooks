#!/usr/bin/env python3
"""Read pinned package versions from pylock.toml for native image builds."""

from __future__ import annotations

import argparse
import platform
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import packaging.markers

_VERSION_FORMATS = frozenset({"pep440", "git-tag", "apache-arrow-branch"})
_DEFAULT_PYLOCK = Path("pylock.toml")


def default_pylock_path() -> Path:
    if _DEFAULT_PYLOCK.is_file():
        return _DEFAULT_PYLOCK
    sibling = Path(__file__).resolve().parent / _DEFAULT_PYLOCK.name
    if sibling.is_file():
        return sibling
    return _DEFAULT_PYLOCK


def default_platform_machine() -> str:
    return platform.machine()


def python_minor_from_path(pylock_path: Path) -> str:
    match = re.search(r"python-(\d+\.\d+)", pylock_path.as_posix())
    if match:
        return match.group(1)
    return "3.12"


def marker_env(*, python_minor: str, platform_machine: str) -> dict[str, str]:
    return {
        "python_full_version": f"{python_minor}.0",
        "python_version": python_minor,
        "implementation_name": "cpython",
        "sys_platform": "linux",
        "platform_machine": platform_machine,
        "platform_system": "Linux",
    }


def load_pylock_packages(pylock_text: str, *, python_minor: str, platform_machine: str) -> dict[str, dict[str, Any]]:
    doc = tomllib.loads(pylock_text)
    env = marker_env(python_minor=python_minor, platform_machine=platform_machine)
    packages: dict[str, dict[str, Any]] = {}
    for package in doc.get("packages", []):
        marker = package.get("marker")
        if marker and not packaging.markers.Marker(marker).evaluate(env):
            continue
        name = package["name"]
        if name in packages:
            raise ValueError(f"duplicate package in lockfile: {name}")
        packages[name] = package
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
    try:
        return packages[package]["version"]
    except KeyError as exc:
        msg = (
            f"package {package!r} not found in {pylock_path} "
            f"for platform_machine={platform_machine!r} python={resolved_python!r}"
        )
        raise SystemExit(msg) from exc


def format_version(version: str, fmt: str) -> str:
    if fmt == "pep440":
        return version
    if fmt == "git-tag":
        return f"v{version}"
    if fmt == "apache-arrow-branch":
        return f"apache-arrow-{version}"
    raise ValueError(f"unsupported format: {fmt}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "positional",
        nargs="+",
        metavar=("PACKAGE", "PYLOCK"),
        help="PACKAGE, or PYLOCK PACKAGE when pylock.toml is not in the cwd",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="platform_machine for marker evaluation (default: runtime machine)",
    )
    parser.add_argument(
        "--python",
        dest="python_minor",
        default=None,
        help="Python minor version for marker evaluation (default: infer from path)",
    )
    parser.add_argument(
        "--format",
        choices=sorted(_VERSION_FORMATS),
        default="pep440",
        help="output format (default: pep440)",
    )
    args = parser.parse_args(argv)

    if len(args.positional) == 1:
        pylock_path = default_pylock_path()
        package = args.positional[0]
    elif len(args.positional) == 2:
        pylock_path = Path(args.positional[0])
        package = args.positional[1]
    else:
        parser.error("expected PACKAGE or PYLOCK PACKAGE")

    version = locked_version(
        pylock_path,
        package,
        python_minor=args.python_minor,
        platform_machine=args.platform or default_platform_machine(),
    )
    print(format_version(version, args.format))
    return 0


if __name__ == "__main__":
    sys.exit(main())
