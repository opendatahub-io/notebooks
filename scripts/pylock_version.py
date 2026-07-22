#!/usr/bin/env python3
"""Read pinned package versions from pylock.toml for native image builds.

Marker evaluation
-----------------
:func:`evaluate_marker` parses PEP 508-style markers with :mod:`ast` and evaluates
them against a restricted whitelist of environment keys (:func:`marker_env`). It
supports nested ``and`` / ``or`` / ``not``, parentheses, ``in`` / ``not in`` tuple
literals, and ``==`` / ``!=`` with ``.*`` wildcards via :func:`fnmatch.fnmatchcase`.

Version-specifier operators (``>=``, ``~=``, etc.) and unknown marker variables
raise :class:`ValueError` instead of silently mis-parsing.

Callers format output in shell: ``v${VERSION}`` or ``apache-arrow-${VERSION}`` for git
branches. When the lock carries a local segment (e.g. torch ``2.7.1+cu128``), strip
only the ``+…`` suffix (``${VERSION%%+*}``) before tagging — that removes local
versions but not pre-releases (``1.0a1`` stays ``1.0a1``). Current native-build
pins are plain releases, so this is sufficient today.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import platform
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

_DEFAULT_PYLOCK = Path("pylock.toml")
_ALLOWED_NAMES = frozenset(
    {
        "python_version",
        "python_full_version",
        "implementation_name",
        "platform_python_implementation",
        "sys_platform",
        "platform_machine",
        "platform_system",
        "os_name",
    }
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
        "os_name": "posix",
    }


def _eval_marker(node: ast.AST, env: dict[str, str]) -> bool | str | tuple[str, ...]:
    match node:
        case ast.Expression(body):
            return _eval_marker(body, env)

        case ast.BoolOp(op=ast.And(), values=values):
            return all(_eval_marker(value, env) for value in values)
        case ast.BoolOp(op=ast.Or(), values=values):
            return any(_eval_marker(value, env) for value in values)

        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _eval_marker(operand, env)

        case ast.Compare(left=left, ops=[op], comparators=[right]):
            left_value = _eval_marker(left, env)
            right_value = _eval_marker(right, env)

            match op:
                case ast.Eq():
                    if isinstance(right_value, str) and right_value.endswith(".*"):
                        return fnmatch.fnmatchcase(left_value, right_value)
                    return left_value == right_value
                case ast.NotEq():
                    if isinstance(right_value, str) and right_value.endswith(".*"):
                        return not fnmatch.fnmatchcase(left_value, right_value)
                    return left_value != right_value
                case ast.In():
                    if not isinstance(right_value, tuple):
                        raise ValueError("'in' requires a tuple literal")
                    return left_value in right_value
                case ast.NotIn():
                    if not isinstance(right_value, tuple):
                        raise ValueError("'not in' requires a tuple literal")
                    return left_value not in right_value
                case _:
                    raise ValueError(f"comparison operator not supported: {op}")

        case ast.Name(id=name):
            if name not in _ALLOWED_NAMES:
                raise ValueError(f"unknown marker variable: {name}")
            return env.get(name, "")

        case ast.Constant(value=str(string_value)):
            return string_value

        case ast.Tuple(elts=elts):
            return tuple(_eval_marker(elt, env) for elt in elts)

        case _:
            raise ValueError(f"unsupported syntax: {ast.dump(node)}")


def evaluate_marker(marker: str, env: dict[str, str]) -> bool:
    """Return whether *marker* matches *env*."""
    try:
        tree = ast.parse(marker, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid marker syntax: {marker!r}") from exc
    result = _eval_marker(tree, env)
    if not isinstance(result, bool):
        raise ValueError(f"marker must evaluate to bool, got {result!r}: {marker!r}")
    return result


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
        metavar="ARG",
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
