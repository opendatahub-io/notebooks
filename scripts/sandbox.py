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
        additional_arguments = [
            # Mount the zigcc utility
            f"--volume={os.getcwd()}/bin/zig-0.15.2:/mnt",
            f"--env=ZIGCC_ARCH={args.platform.split('/')[1]}",
            "--unsetenv=ZIGCC_ARCH",
            # CMake heeds these
            "--env=CC=/mnt/clang",
            "--env=CXX=/mnt/clang++",
            "--unsetenv=CC",
            "--unsetenv=CXX",
            # CMake ignores these
            "--env=AR=/mnt/llvm-ar",
            "--env=RANLIB=/mnt/llvm-ranlib",
            "--env=STRIP=/mnt/llvm-strip",
            "--unsetenv=AR",
            "--unsetenv=RANLIB",
            "--unsetenv=STRIP",
            # Workaround for a s390x compilation issue

            # Codeserver: SPDLOG_CONSTEXPR_FUNC is to work around a consteval issue with zig c++
            #  ../deps/spdlog/include/spdlog/details/fmt_helper.h:105:54: error: call to consteval function 'fmt::basic_format_string<...>' is not a constant expression
            #  Clang (via Zig) is stricter about consteval requirements than GCC
            #  The format string "{:02}" cannot be evaluated as a constant expression in this context

            "--env=CXXFLAGS=-Dundefined=64 -DFMT_CONSTEVAL= -DSPDLOG_CONSTEXPR_FUNC=",
            # "--unsetenv=CFLAGS",
            "--unsetenv=CXXFLAGS",

            tmpdir,
        ]
        command = []
        for arg in args.remaining[1:]:
            if arg == "{};":
                command.extend(additional_arguments)
            else:
                command.append(arg)
        print(f"running {command=}")
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as err:
            log.error("Failed to execute process", command=err.cmd, returncode=err.returncode)
            return err.returncode
    return 0

"""
Downloading jedi
  × Failed to build `pyzmq==27.1.0`
  ├─▶ The build backend returned an error
  ╰─▶ Call to `scikit_build_core.build.build_wheel` failed (exit status: 1)
      [stdout]
      *** scikit-build-core 0.11.6 using CMake 3.26.5 (wheel)
      *** Configuring CMake...
      loading initial cache file /tmp/tmpf9bnfh5o/build/CMakeInit.txt
      -- Configuring incomplete, errors occurred!
      [stderr]
      CMake Error at /usr/share/cmake/Modules/CMakeDetermineCCompiler.cmake:49
      (message):
        Could not find compiler set in environment variable CC:
        /mnt/zig-0.15.1/zig cc -target s390x-linux-gnu.
      Call Stack (most recent call first):
        CMakeLists.txt:2 (project)
"""

"""
creating build/temp.linux-s390x-cpython-312/psutil/arch/linux
      /mnt/zig cc -target s390x-linux-gnu -fno-strict-overflow
      -Wsign-compare -DDYNAMIC_ANNOTATIONS_ENABLED=1 -DNDEBUG
      -O2 -fexceptions -g -grecord-gcc-switches -pipe
      -Wall -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2
      -Wp,-D_GLIBCXX_ASSERTIONS -fstack-protector-strong
      -m64 -march=z14 -mtune=z15 -fasynchronous-unwind-tables
      -fstack-clash-protection -O2 -fexceptions -g -grecord-gcc-switches
      -pipe -Wall -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2
      -Wp,-D_GLIBCXX_ASSERTIONS -fstack-protector-strong
      -m64 -march=z14 -mtune=z15 -fasynchronous-unwind-tables
      -fstack-clash-protection -O2 -fexceptions -g -grecord-gcc-switches
      -pipe -Wall -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2
      -Wp,-D_GLIBCXX_ASSERTIONS -fstack-protector-strong
      -m64 -march=z14 -mtune=z15 -fasynchronous-unwind-tables
      -fstack-clash-protection -fPIC -DPSUTIL_POSIX=1 -DPSUTIL_SIZEOF_PID_T=4
      -DPSUTIL_VERSION=700 -DPy_LIMITED_API=0x03060000
      -DPSUTIL_LINUX=1 -I/tmp/.tmpWlL4ZP/builds-v0/.tmpOwAhw2/include
      -I/usr/include/python3.12 -c psutil/_psutil_common.c -o
      build/temp.linux-s390x-cpython-312/psutil/_psutil_common.o
      [stderr]
      /tmp/.tmpWlL4ZP/builds-v0/.tmpOwAhw2/lib64/python3.12/site-packages/setuptools/dist.py:759:
      SetuptoolsDeprecationWarning: License classifiers are deprecated.
      !!

      ********************************************************************************
              Please consider removing the following classifiers in favor of a
      SPDX license expression:
              License :: OSI Approved :: BSD License
              See
      https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license
      for details.

      ********************************************************************************
      !!
        self._finalize_license_expression()
      error: unsupported preprocessor arg: -D_FORTIFY_SOURCE
"""

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
    if not (ROOT_DIR / "bin/zig-0.15.2").exists():
        subprocess.check_call([MAKE, "bin/zig-0.15.2"], cwd=ROOT_DIR)
    if not (ROOT_DIR / "bin/zig-0.15.2/zigcc").exists():
        subprocess.check_call([MAKE, "build"], cwd=ROOT_DIR / "scripts/zigcc")
    # Openblas failed to compile
    # https://github.com/OpenMathLib/OpenBLAS/discussions/5169#discussioncomment-12489095
    # During shared library creation: The exports/Makefile checks the compiler name to decide whether to add -lomp (clang) or -lgomp (gcc)
    # When compiler is named "cc": Detection fails → no OpenMP library appended → linking fails
    # ld.lld: error: undefined reference: omp_get_max_threads
    # >>> referenced by ../libopenblasp-r0.3.30.so (disallowed by --no-allow-shlib-undefined)
    # to fix this, name the compiler binary alias "clang" and "clang++"
    for alias in ["clang", "clang++", "ar", "llvm-ar", "ranlib", "llvm-ranlib", "strip", "llvm-strip"]:
        shutil.copy(ROOT_DIR / "scripts/zigcc/bin/zigcc", ROOT_DIR / "bin/zig-0.15.2" / alias)
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

    _copy_tree_dir(
        src,
        dst,
        pathlib.Path("."),
        repo_base_rel,
        root_only_ignore,
        any_depth_ignore,
        frozenset(),
    )


def _copy_tree_dir(
        src_dir: pathlib.Path,
        dst_dir: pathlib.Path,
        rel: pathlib.Path,
        repo_base_rel: pathlib.Path,
        root_only_ignore: set[str],
        any_depth_ignore: set[str],
        ancestor_realpaths: frozenset[str],
) -> None:
    real_dir = os.path.realpath(src_dir)
    if real_dir in ancestor_realpaths:
        return

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        log.warning(f"cannot create directory, skipping subtree: {rel}")
        return

    parent_at_repo_root = len((repo_base_rel / rel).parts) == 0
    chain = ancestor_realpaths | {real_dir}

    try:
        entries = list(os.scandir(src_dir))
    except OSError as err:
        log.warning(f"cannot read directory, skipping subtree: {rel}", error=str(err))
        return

    for entry in entries:
        name = entry.name
        if entry.is_dir(follow_symlinks=True):
            if _ignore_dirname(
                name,
                root_only_ignore=root_only_ignore,
                any_depth_ignore=any_depth_ignore,
                parent_at_repo_root=parent_at_repo_root,
            ):
                continue
            _copy_tree_dir(
                pathlib.Path(entry.path),
                dst_dir / name,
                rel / name,
                repo_base_rel,
                root_only_ignore,
                any_depth_ignore,
                chain,
            )
        elif entry.is_file(follow_symlinks=True):
            try:
                shutil.copy(entry.path, dst_dir / name)
            except PermissionError:
                log.warning(f"cannot copy file, skipping: {rel / name}")


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
