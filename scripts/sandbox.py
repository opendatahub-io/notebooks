#! /usr/bin/env python3

import argparse
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import cast, Literal

import structlog

from ci.logging_config import configure_logging

ROOT_DIR = pathlib.Path(__file__).parent.parent
MAKE = shutil.which("gmake") or shutil.which("make")

log = structlog.get_logger()


class Args(argparse.Namespace):
    dockerfile: pathlib.Path
    platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"]
    remaining: list[str]


def main() -> int:
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument("--dockerfile", type=pathlib.Path, required=True)
    p.add_argument("--platform", type=str,
                   choices=["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"],
                   required=True)
    p.add_argument('remaining', nargs=argparse.REMAINDER)

    args = cast(Args, p.parse_args())

    print(f"{__file__=} started with {args=}")

    if not args.remaining or args.remaining[0] != "--":
        print("must specify command to execute after double dashes at the end, such as `-- command --args ...`")
        return 1
    if not "{};" in args.remaining:
        print("must give a `{};` parameter that will be replaced with new build context")
        return 1

    build_args = extract_build_args(args.remaining[1:])
    prereqs = buildinputs(dockerfile=args.dockerfile, platform=args.platform, build_args=build_args)

    with tempfile.TemporaryDirectory(delete=True) as tmpdir:
        setup_sandbox(prereqs, pathlib.Path(tmpdir))
        command = [arg if arg != "{};" else tmpdir for arg in args.remaining[1:]]
        print(f"running {command=}")
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as err:
            log.error("Failed to execute process", command=err.cmd, returncode=err.returncode)
            return err.returncode
    return 0


def extract_build_args(remaining: list[str]) -> dict[str, str]:
    """Extract --build-arg KEY=VALUE pairs from the command line using argparse."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--build-arg", action="append", default=[])
    known, _ = parser.parse_known_args(remaining)
    build_args = {}
    for arg in known.build_arg:
        if "=" not in arg:
            raise ValueError(f"--build-arg must be in KEY=VALUE format, got: {arg!r}")
        key, value = arg.split("=", 1)
        build_args[key] = value
    return build_args


def buildinputs(
        dockerfile: pathlib.Path | str,
        platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"] = "linux/amd64",
        build_args: dict[str, str] | None = None
) -> list[pathlib.Path]:
    if not (ROOT_DIR / "bin/buildinputs").exists():
        subprocess.check_call([MAKE, "bin/buildinputs"], cwd=ROOT_DIR)
    if not build_args:
        build_args = {}
    stdout = subprocess.check_output([ROOT_DIR / "bin/buildinputs",
                                      *[f"-build-arg={k}={v}" for k, v in build_args.items()],
                                      str(dockerfile)],
                                     text=True, cwd=ROOT_DIR,
                                     env={**os.environ, "TARGETPLATFORM": platform})
    prereqs = list(dict.fromkeys(pathlib.Path(file) for file in json.loads(stdout)))
    print(f"{prereqs=}")
    return prereqs


def _load_dockerignore(root: pathlib.Path) -> list[str]:
    """Read .dockerignore from *root* and return the non-comment, non-empty lines."""
    dockerignore = root / ".dockerignore"
    if not dockerignore.exists():
        return []
    return [
        stripped
        for line in dockerignore.read_text().splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#") and not stripped.startswith("!")
    ]


def _ignored_dir_names(root: pathlib.Path) -> tuple[set[str], set[str]]:
    """Return directory-name sets for .dockerignore pruning during os.walk.

    Returns ``(root_only, any_depth)``:

    * ``**/name/`` patterns apply at any depth (e.g. ``**/node_modules/``).
    * bare ``name/`` patterns apply only when the directory sits at the
      repository root (e.g. top-level ``ci/``), matching Docker semantics.

    Multi-segment paths (e.g. ``a/b/``) and file-glob patterns (e.g. ``*.log``)
    are excluded.

    TODO: negation patterns (``!name``) are filtered out, not honored as re-inclusions.
    """
    root_only: set[str] = set()
    any_depth: set[str] = set()
    for pattern in _load_dockerignore(root):
        if not pattern.endswith("/"):
            continue
        is_globstar = pattern.startswith("**/")
        name = pattern.removeprefix("**/").removesuffix("/")
        if name and "/" not in name and not any(c in name for c in ("*", "?", "[")):
            (any_depth if is_globstar else root_only).add(name)
    return root_only, any_depth


def _ignore_dirname(
        dirname: str,
        *,
        root_only_ignore: set[str],
        any_depth_ignore: set[str],
        parent_at_repo_root: bool,
) -> bool:
    if dirname in any_depth_ignore:
        return True
    return dirname in root_only_ignore and parent_at_repo_root


def _copy_tree(
        src: pathlib.Path,
        dst: pathlib.Path,
        *,
        repo_base_rel: pathlib.Path | None = None,
        root_only_ignore: set[str] | None = None,
        any_depth_ignore: set[str] | None = None,
):
    """Copy a directory tree, copying only file content (no metadata/xattrs).

    shutil.copytree's internal copystat() on directories fails on macOS with
    EPERM when extended attributes (quarantine, etc.) cannot be reproduced
    on the destination.  Walking manually with shutil.copy avoids this.
    Directories that cannot be created (e.g. macOS EPERM on certain dotfiles
    in temp directories) are logged and skipped.

    Ignore sets follow ``_ignored_dir_names`` / ``.dockerignore`` semantics.
    """
    root_only_ignore = root_only_ignore or set()
    any_depth_ignore = any_depth_ignore or set()
    if repo_base_rel is None:
        repo_base_rel = src.relative_to(ROOT_DIR) if src.is_relative_to(ROOT_DIR) else pathlib.Path()

    if src.name in any_depth_ignore:
        return
    if src.name in root_only_ignore and len(repo_base_rel.parts) == 1:
        return

    visited: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(src, followlinks=True):
        real_dir = os.path.realpath(dirpath)
        if real_dir in visited:
            dirnames.clear()
            continue
        visited.add(real_dir)

        rel = pathlib.Path(dirpath).relative_to(src)
        parent_at_repo_root = len((repo_base_rel / rel).parts) == 0
        dirnames[:] = [
            d for d in dirnames
            if not _ignore_dirname(
                d,
                root_only_ignore=root_only_ignore,
                any_depth_ignore=any_depth_ignore,
                parent_at_repo_root=parent_at_repo_root,
            )
        ]
        try:
            (dst / rel).mkdir(parents=True, exist_ok=True)
        except PermissionError:
            log.warning(f"cannot create directory, skipping subtree: {rel}")
            dirnames.clear()
            continue
        for fname in filenames:
            try:
                shutil.copy(pathlib.Path(dirpath) / fname, dst / rel / fname)
            except PermissionError:
                log.warning(f"cannot copy file, skipping: {rel / fname}")


def setup_sandbox(prereqs: list[pathlib.Path], tmpdir: pathlib.Path):
    gitignore = ROOT_DIR / ".gitignore"
    if gitignore.exists():
        shutil.copy(gitignore, tmpdir)

    root_only_ignore, any_depth_ignore = _ignored_dir_names(ROOT_DIR)

    for dep in prereqs:
        if dep.is_absolute():
            dep = dep.relative_to(ROOT_DIR)

        # Expand glob patterns (e.g. "dir/*.patch" from Dockerfile COPY instructions).
        # The buildinputs tool emits these patterns verbatim from COPY/ADD directives,
        # so we must expand them here before the existence check — a literal path like
        # "patches/*.patch" does not exist on disk and would otherwise trigger sys.exit(1).
        if any(c in str(dep) for c in ('*', '?', '[')):
            matched = sorted(glob.glob(str(dep)))
            if not matched:
                log.warning(f"glob pattern matched no files: {dep}")
                continue
            for m in matched:
                m_path = pathlib.Path(m)
                (tmpdir / m_path.parent).mkdir(parents=True, exist_ok=True)
                if m_path.is_dir():
                    _copy_tree(
                        m_path,
                        tmpdir / m_path,
                        repo_base_rel=m_path,
                        root_only_ignore=root_only_ignore,
                        any_depth_ignore=any_depth_ignore,
                    )
                else:
                    shutil.copy(m_path, tmpdir / m_path.parent)
            continue

        if not dep.exists():
            log.error(f"File or directory '{dep}' referenced in the Dockerfile was not found on disk. Please ensure the file exists.")
            sys.exit(1)

        if dep.is_dir():
            _copy_tree(
                dep,
                tmpdir / dep,
                repo_base_rel=dep,
                root_only_ignore=root_only_ignore,
                any_depth_ignore=any_depth_ignore,
            )
        else:
            (tmpdir / dep.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy(dep, tmpdir / dep.parent)


if __name__ == '__main__':
    configure_logging()
    sys.exit(main())
