#!/usr/bin/env python3

"""Generate Python dependency lock files (pylock.toml) using uv pip compile.

This script generates Python dependency lock files (pylock.toml) for multiple
directories using either internal Red Hat wheel indexes or the public PyPI index.

Features:
  - Supports multiple Python project directories, detected by pyproject.toml.
  - Detects available Dockerfile flavors (CPU, CUDA, ROCm) for rh-index mode.
  - Validates Python version extracted from directory name (expects format .../ubi9-python-X.Y).
  - Generates per-flavor locks in 'uv.lock.d/' for rh-index mode.
  - Overwrites existing pylock.toml in-place for public PyPI index mode.

Index Modes:
  auto (default) -- Uses rh-index if uv.lock.d/ exists, public-index otherwise.
  rh-index       -- Uses internal Red Hat wheel indexes. Generates uv.lock.d/pylock.<flavor>.toml.
  public-index   -- Uses public PyPI index and updates pylock.toml in place.

Fallback Index (RHAIENG-3071):
  For CUDA and ROCm flavors, if CPU_INDEX_URL is defined in the build-args/*.conf file,
  it will be added as a fallback index for packages not available in the specialized indexes.
  The resolver also enables `--index-strategy=unsafe-best-match` for these cases,
  so uv can select versions from fallback indexes when needed.

Usage:
  1. Lock using auto mode (default) for all projects in MAIN_DIRS::

       python pylocks_generator.py

  2. Lock using rh-index for a specific directory::

       python pylocks_generator.py rh-index jupyter/minimal/ubi9-python-3.12

  3. Lock using public index for a specific directory::

       python pylocks_generator.py public-index jupyter/minimal/ubi9-python-3.12

  4. Force upgrade all packages to latest versions::

       FORCE_LOCKFILES_UPGRADE=1 python pylocks_generator.py

Notes:
  - If the script fails for a directory, it lists the failed directories at the end.
  - Public index mode does not create uv.lock.d directories and keeps the old format.
  - Python version extraction depends on directory naming convention; invalid formats are skipped.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

# =============================================================================
# CONFIGURATION
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
UV = ROOT_DIR / "uv"
CVE_CONSTRAINTS_FILE = ROOT_DIR / "dependencies" / "cve-constraints.txt"
PUBLIC_INDEX = "--default-index=https://pypi.org/simple"
MAIN_DIRS = ("jupyter", "runtimes", "rstudio", "codeserver")
UV_MIN_VERSION = (0, 4, 0)

NO_EMIT_PACKAGES = (
    "odh-notebooks-meta-llmcompressor-deps",
    "odh-notebooks-meta-runtime-elyra-deps",
    "odh-notebooks-meta-runtime-datascience-deps",
    "odh-notebooks-meta-workbench-datascience-deps",
)

FLAVORS = ("cpu", "cuda", "rocm")


class IndexMode(str, Enum):
    auto = "auto"
    rh_index = "rh-index"
    public_index = "public-index"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"🔹 {BLUE}{msg}{RESET}")


def warn(msg: str) -> None:
    print(f"⚠️ {YELLOW}{msg}{RESET}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"❌ {RED}{msg}{RESET}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"✅ {GREEN}{msg}{RESET}", file=sys.stderr)


def read_conf_value(conf_file: Path, key: str) -> str | None:
    """Read a key=value from a .conf file, skipping comments and blank lines."""
    for line in conf_file.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


# =============================================================================
# PRE-FLIGHT CHECK
# =============================================================================


def check_uv() -> None:
    """Verify the uv wrapper exists and meets the minimum version requirement."""
    if not UV.is_file() or not os.access(UV, os.X_OK):
        error(f"Expected uv wrapper at '{UV}' but it is missing or not executable.")
        raise SystemExit(1)

    try:
        result = subprocess.run(
            [str(UV), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        version_str = result.stdout.strip().split()[1] if result.stdout.strip() else "0.0.0"
    except (IndexError, FileNotFoundError):
        version_str = "0.0.0"

    version_tuple = tuple(int(x) for x in version_str.split("."))
    if version_tuple < UV_MIN_VERSION:
        min_ver = ".".join(str(x) for x in UV_MIN_VERSION)
        error(f"uv version {version_str} found, but >= {min_ver} is required.")
        error("Please upgrade uv: https://github.com/astral-sh/uv")
        raise SystemExit(1)


# =============================================================================
# TARGET DIRECTORY DISCOVERY
# =============================================================================


def find_target_dirs(target_dir: Path | None) -> list[Path]:
    """Find directories containing pyproject.toml."""
    if target_dir is not None:
        return [target_dir]

    info("Scanning main directories for Python projects...")
    dirs: set[Path] = set()
    for base_name in MAIN_DIRS:
        base = ROOT_DIR / base_name
        if base.is_dir():
            dirs.update(p.parent for p in base.rglob("pyproject.toml"))
    return sorted(dirs)


# =============================================================================
# FLAVOR DETECTION
# =============================================================================


def detect_flavors(project_dir: Path) -> set[str]:
    """Detect available Dockerfile flavors (cpu, cuda, rocm) in a directory."""
    return {f for f in FLAVORS if (project_dir / f"Dockerfile.{f}").is_file()}


def extract_python_version(project_dir: Path) -> str | None:
    """Extract Python version from directory name suffix (e.g. ubi9-python-3.12 -> 3.12)."""
    name = project_dir.resolve().name
    # The version is everything after the last hyphen
    version = name.rsplit("-", maxsplit=1)[-1]
    if re.fullmatch(r"\d+\.\d+", version):
        return version
    return None


# =============================================================================
# INDEX FLAGS
# =============================================================================


def get_index_flags(project_dir: Path, flavor: str) -> list[str] | None:
    """Build uv index flags from build-args/<flavor>.conf.

    Returns None on failure (missing conf or INDEX_URL).
    """
    conf_file = project_dir / "build-args" / f"{flavor}.conf"
    if not conf_file.is_file():
        warn(f"Missing build-args config for {flavor}: {conf_file}")
        return None

    index_url = read_conf_value(conf_file, "INDEX_URL")
    if not index_url:
        warn(f"INDEX_URL not found in {conf_file}")
        return None

    flags = [f"--default-index={index_url}", f"--index={index_url}"]

    # For CUDA and ROCm flavors, add CPU index as fallback (RHAIENG-3071).
    # uv defaults to `first-index`, which can block true fallback when a package
    # exists on the primary index but not at a compatible version.
    if flavor in ("cuda", "rocm"):
        cpu_index_url = read_conf_value(conf_file, "CPU_INDEX_URL")
        if cpu_index_url:
            flags.append(f"--index={cpu_index_url}")
            flags.append("--index-strategy=unsafe-best-match")
            print(
                "  📎 Using CPU index as fallback (--index-strategy=unsafe-best-match)",
                file=sys.stderr,
            )

    return flags


# =============================================================================
# LOCK FILE GENERATION
# =============================================================================


def run_lock(
    project_dir: Path,
    flavor: str,
    index_flags: list[str],
    mode: IndexMode,
    python_version: str,
    upgrade: bool,
) -> bool:
    """Run uv pip compile to generate a lock file. Returns True on success."""
    if mode == IndexMode.public_index:
        output = "pylock.toml"
        desc = "pylock.toml (public index)"
        print("➡️ Generating pylock.toml from public PyPI index...")
    else:
        (project_dir / "uv.lock.d").mkdir(exist_ok=True)
        output = f"uv.lock.d/pylock.{flavor}.toml"
        desc = f"{flavor.upper()} lock file"
        print(f"➡️ Generating {flavor.upper()} lock file...")

    # Tag filtering was added in uv 0.9.16 (https://github.com/astral-sh/uv/pull/16956)
    # but bypassed in --universal mode. uv 0.10.5 (https://github.com/astral-sh/uv/pull/18081)
    # now filters wheels by requires-python and marker disjointness even in --universal mode.
    # Documentation at https://docs.astral.sh/uv/reference/cli/#uv-pip-compile--python-platform says that
    #  `--python-platform linux` is alias for `x86_64-unknown-linux-gnu`; we cannot use this to get a multiarch pylock
    # Let's use --universal temporarily, and in the future we can switch to using uv.lock
    #  when https://github.com/astral-sh/uv/issues/6830 is resolved, or symlink `ln -s uv.lock.d/uv.${flavor}.lock uv.lock`
    # Note: currently generating uv.lock.d/pylock.${flavor}.toml; future rename to uv.${flavor}.lock is planned
    # See also --universal discussion with Gerard
    #  https://redhat-internal.slack.com/archives/C0961HQ858Q/p1757935641975969?thread_ts=1757542802.032519&cid=C0961HQ858Q
    cmd: list[str] = [
        str(UV),
        "pip",
        "compile",
        "pyproject.toml",
        "--output-file",
        output,
        "--format",
        "pylock.toml",
        "--generate-hashes",
        "--emit-index-url",
        f"--python-version={python_version}",
        "--universal",
        "--no-annotate",
        "--quiet",
    ]

    for pkg in NO_EMIT_PACKAGES:
        cmd.extend(["--no-emit-package", pkg])

    if upgrade:
        cmd.append("--upgrade")

    # Use relative path to avoid absolute paths in pylock.toml headers
    if CVE_CONSTRAINTS_FILE.is_file():
        relative_constraints = os.path.relpath(CVE_CONSTRAINTS_FILE, project_dir)
        cmd.extend(["--constraints", relative_constraints])

    cmd.extend(index_flags)

    result = subprocess.run(cmd, cwd=project_dir, check=False)

    if result.returncode != 0:
        warn(f"Failed to generate {desc} in {project_dir}")
        output_path = project_dir / output
        output_path.unlink(missing_ok=True)
        return False

    ok(f"{desc} generated successfully.")
    return True


# =============================================================================
# MAIN
# =============================================================================

app = typer.Typer(add_completion=False)


@app.command()
def main(
    index_mode: Annotated[
        IndexMode, typer.Argument(help="Index mode: auto, rh-index, or public-index")
    ] = IndexMode.auto,
    target_dir: Annotated[
        Path | None, typer.Argument(help="Specific project directory to process")
    ] = None,
) -> None:
    """Generate pylock.toml lock files for Python project directories."""
    # PRE-FLIGHT
    check_uv()

    # UPGRADE FLAG
    upgrade = os.environ.get("FORCE_LOCKFILES_UPGRADE", "0") == "1"
    if upgrade:
        info("FORCE_LOCKFILES_UPGRADE=1 detected. Will upgrade all packages to latest versions.")

    info(f"Using index mode: {index_mode.value}")

    # TARGET DIRECTORIES
    target_dirs = find_target_dirs(target_dir)
    if not target_dirs:
        error("No directories containing pyproject.toml were found.")
        raise SystemExit(1)

    # MAIN LOOP
    success_dirs: list[Path] = []
    failed_dirs: list[Path] = []

    for tdir in target_dirs:
        print()
        print("=" * 67)
        info(f"Processing directory: {tdir}")
        print("=" * 67)

        python_version = extract_python_version(tdir)
        if python_version is None:
            warn(f"Could not extract valid Python version from directory name: {tdir}")
            warn("Expected directory format: .../ubi9-python-X.Y")
            continue

        flavors = detect_flavors(tdir)
        if not flavors:
            warn(f"No Dockerfiles found in {tdir} (cpu/cuda/rocm). Skipping.")
            continue

        print(f"📦 Python version: {python_version}")
        print("🧩 Detected flavors:")
        for f in sorted(flavors):
            print(f"  • {f.upper()}")
        print()

        # Resolve effective mode
        if index_mode == IndexMode.auto:
            effective_mode = IndexMode.rh_index if (tdir / "uv.lock.d").is_dir() else IndexMode.public_index
        else:
            effective_mode = index_mode
        info(f"Effective mode for this directory: {effective_mode.value}")

        dir_success = True

        if effective_mode == IndexMode.public_index:
            if not run_lock(tdir, "cpu", [PUBLIC_INDEX], effective_mode, python_version, upgrade):
                dir_success = False
        else:
            for flavor in ("cpu", "cuda", "rocm"):
                if flavor not in flavors:
                    continue
                flags = get_index_flags(tdir, flavor)
                if flags is None:
                    dir_success = False
                    continue
                if not run_lock(tdir, flavor, flags, effective_mode, python_version, upgrade):
                    dir_success = False

        if dir_success:
            success_dirs.append(tdir)
        else:
            failed_dirs.append(tdir)

    # SUMMARY
    print()
    print("=" * 67)
    ok("Lock generation complete.")
    print("=" * 67)

    if success_dirs:
        print("✅ Successfully generated locks for:")
        for d in success_dirs:
            print(f"  • {d}")

    if failed_dirs:
        print()
        warn("Failed lock generation for:")
        for d in failed_dirs:
            print(f"  • {d}")
            print("Please comment out the missing package to continue and report the missing package to the RH index maintainers")
        raise SystemExit(1)


if __name__ == "__main__":
    app()
