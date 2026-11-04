#!/usr/bin/env python3
"""Make TensorBoard 2.20 start on setuptools>=82.

TensorBoard 2.21 dropped ``pkg_resources`` (tensorflow/tensorboard#7057). AIPCC
still ships 2.20, and these images keep ``setuptools>=83`` (RHAIENG-6408), which
no longer provides that module. ``tensorboard`` imports it while loading the
data-server ingester, so ``--load_fast=auto`` never reaches the Python fallback
after the non-FIPS Rust binary is removed (RHAIENG-7875).

This applies the 2.21 import change to the two modules that still import
``pkg_resources``. It is a no-op once those imports are gone, and it fails the
image build if a 2.20 tree does not match the expected snippets.
"""

from __future__ import annotations

import pathlib
import sys

DEFAULT_SITE_PACKAGES = pathlib.Path("/opt/app-root/lib/python3.12/site-packages")

_DEFAULT_IMPORT_OLD = "import logging\n\nimport pkg_resources\n"
_DEFAULT_IMPORT_NEW = "import logging\nfrom importlib import metadata\n"

_DEFAULT_PLUGINS_OLD = """\
    return [
        entry_point.resolve()
        for entry_point in pkg_resources.iter_entry_points(
            "tensorboard_plugins"
        )
    ]
"""

_DEFAULT_PLUGINS_NEW = """\
    return [
        entry_point.load()
        for entry_point in _iter_entry_points("tensorboard_plugins")
    ]


def _iter_entry_points(group):
    \"\"\"Returns entry points for a given group across Python versions.\"\"\"
    entry_points = metadata.entry_points()
    # Python 3.10+ returns an EntryPoints object. Older releases returned a dict.
    if hasattr(entry_points, "select"):
        return entry_points.select(group=group)
    return entry_points.get(group, ())
"""

_SERVER_IMPORT_OLD = "import pkg_resources\n"
_SERVER_IMPORT_NEW = "from packaging import version as packaging_version\n"
_SERVER_PARSE_OLD = "pkg_resources.parse_version"
_SERVER_PARSE_NEW = "packaging_version.parse"
_SERVER_PARSE_COUNT = 2


class TensorBoardPatchError(RuntimeError):
    """Installed TensorBoard sources are not 2.20 and are not already compatible."""


def patch_site_packages(site_packages: pathlib.Path) -> None:
    """Patch TensorBoard 2.20 under ``site_packages`` so it does not import pkg_resources."""
    default_py = site_packages / "tensorboard" / "default.py"
    server_py = site_packages / "tensorboard" / "data" / "server_ingester.py"
    for path in (default_py, server_py):
        if not path.is_file():
            msg = f"TensorBoard source not found: {path}"
            raise TensorBoardPatchError(msg)

    _write_if_changed(default_py, _patch_default(default_py.read_text(encoding="utf-8")))
    _write_if_changed(server_py, _patch_server(server_py.read_text(encoding="utf-8")))


def _patch_default(source: str) -> str:
    if "pkg_resources" not in source:
        return source
    updated = _replace_once(source, _DEFAULT_IMPORT_OLD, _DEFAULT_IMPORT_NEW, "tensorboard/default.py import")
    updated = _replace_once(updated, _DEFAULT_PLUGINS_OLD, _DEFAULT_PLUGINS_NEW, "tensorboard/default.py plugins")
    _require_pkg_resources_gone(updated, "tensorboard/default.py")
    return updated


def _patch_server(source: str) -> str:
    if "pkg_resources" not in source:
        return source
    updated = _replace_once(
        source,
        _SERVER_IMPORT_OLD,
        _SERVER_IMPORT_NEW,
        "tensorboard/data/server_ingester.py import",
    )
    count = updated.count(_SERVER_PARSE_OLD)
    if count != _SERVER_PARSE_COUNT:
        msg = (
            "tensorboard/data/server_ingester.py: expected "
            f"{_SERVER_PARSE_COUNT} pkg_resources.parse_version calls, found {count}"
        )
        raise TensorBoardPatchError(msg)
    updated = updated.replace(_SERVER_PARSE_OLD, _SERVER_PARSE_NEW)
    _require_pkg_resources_gone(updated, "tensorboard/data/server_ingester.py")
    return updated


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        msg = f"{label}: expected exactly one TensorBoard 2.20 snippet, found {count}"
        raise TensorBoardPatchError(msg)
    return source.replace(old, new, 1)


def _require_pkg_resources_gone(source: str, label: str) -> None:
    if "pkg_resources" in source:
        msg = f"{label}: pkg_resources references remain after patching"
        raise TensorBoardPatchError(msg)
    compile(source, label, "exec")


def _write_if_changed(path: pathlib.Path, updated: str) -> None:
    current = path.read_text(encoding="utf-8")
    if updated == current:
        return
    path.write_text(updated, encoding="utf-8")
    cache_dir = path.parent / "__pycache__"
    if cache_dir.is_dir():
        for bytecode in cache_dir.glob(f"{path.stem}.*.pyc"):
            bytecode.unlink()


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv if argv is None else argv)
    site_packages = pathlib.Path(args[1]) if len(args) > 1 else DEFAULT_SITE_PACKAGES
    try:
        patch_site_packages(site_packages)
    except TensorBoardPatchError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
