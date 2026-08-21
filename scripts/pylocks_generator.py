#!/usr/bin/env python3

"""Generate Python dependency lock files (pylock.toml) using uv pip compile.

This script generates Python dependency lock files (pylock.toml) for multiple
directories using either internal Red Hat wheel indexes or the public PyPI index.

Features:
  - Supports multiple Python project directories, detected by pyproject.toml.
  - Detects available Dockerfile.konflux.* flavors (CPU, CUDA, ROCm) for rh-index mode.
  - Validates Python version extracted from directory name (expects format .../ubi9-python-X.Y).
  - Generates per-flavor locks in 'uv.lock.d/' for rh-index mode.
  - Overwrites existing pylock.toml in-place for public PyPI index mode.

Index Modes:
  auto (default) -- Uses rh-index if uv.lock.d/ exists, public-index otherwise.
  rh-index       -- Uses internal Red Hat wheel indexes. Generates uv.lock.d/pylock.<flavor>.toml.
  public-index   -- Uses public PyPI index and updates pylock.toml in place,
                    then converts it to requirements.cpu.txt.

Usage:
  1. Lock using auto mode (default) for all projects in MAIN_DIRS::

       python pylocks_generator.py

  2. Lock using rh-index for a specific directory::

       python pylocks_generator.py rh-index jupyter/minimal/ubi9-python-3.12

  3. Lock using public index for a specific directory::

       python pylocks_generator.py public-index jupyter/minimal/ubi9-python-3.12

  4. Force upgrade all packages to latest versions::

       FORCE_LOCKFILES_UPGRADE=1 python pylocks_generator.py

  5. Only regenerate requirements.txt from existing pylock files (no lock refresh)::

       python pylocks_generator.py --requirements-only
       python pylocks_generator.py rh-index jupyter/minimal/ubi9-python-3.12 --requirements-only

  6. PR-scoped lock regen (CI only; skips dirs whose lock chain the PR did not touch)::

       PYLOCKS_CI_CHECK=1 python pylocks_generator.py auto --pr-base origin/main

Reproducible CI checks (PYLOCKS_CI_CHECK):
  When ``PYLOCKS_CI_CHECK=1`` (set only by ``check-generated-code`` in CI),
  ``uv pip compile`` always passes ``--exclude-newer`` parsed from the existing
  lockfile header when present (CI check mode), else the run's UTC ``now``, so
  regeneration matches the committed tree despite index churn.  Local runs and
  lock renewal omit this variable and use a single UTC ``now`` for the whole run.

  For **Red Hat wheel indexes** (``rh-index``), the lock generator appends
  ``?format=json`` to index URLs so Pulp returns PEP 691 JSON (with
  ``upload-time``) instead of HTML.  This works around AIPCC-12921: Pulp's
  content negotiation ignores Accept header quality values and returns HTML
  whenever ``text/html`` appears, which uv always includes as a fallback.

Notes:
  - If the script fails for a directory, it lists the failed directories at the end.
  - Public index mode does not create uv.lock.d directories and keeps the old format.
  - Public index mode also writes requirements.cpu.txt from the root pylock.toml.
  - Python version extraction depends on directory naming convention; invalid formats are skipped.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import packaging.requirements
import packaging.utils
import typer

from scripts.index_url_resolver import IndexResolutionError, ResolvedIndexConfig, resolve_index_config

# region Configuration
ROOT_DIR = Path(__file__).resolve().parent.parent
UV = ROOT_DIR / "uv"
CONSTRAINTS_FILE = ROOT_DIR / "dependencies" / "constraints.txt"
OVERRIDES_FILE = ROOT_DIR / "dependencies" / "overrides.txt"
PYLOCK_TO_REQUIREMENTS = ROOT_DIR / "scripts" / "lockfile-generators" / "helpers" / "pylock-to-requirements.py"
PUBLIC_INDEX = "--default-index=https://pypi.org/simple"
MAIN_DIRS = ("jupyter", "runtimes", "codeserver", "codeserver-baseline")
# Shared lock inputs: a PR touching any of these regenerates all image project locks.
GLOBAL_LOCK_INPUTS: tuple[Path, ...] = (
    Path("dependencies/constraints.txt"),
    Path("dependencies/overrides.txt"),
    Path("scripts/pylocks_generator.py"),
    Path("scripts/index_url_resolver.py"),
)
UV_MIN_VERSION = (0, 4, 0)

NO_EMIT_PACKAGES = (
    "odh-notebooks-meta-db-connectors-deps",
    "odh-notebooks-meta-jupyterlab-datascience-deps",
    "odh-notebooks-meta-jupyterlab-deps",
    "odh-notebooks-meta-llmcompressor-deps",
    "odh-notebooks-meta-runtime-elyra-deps",
    "odh-notebooks-meta-runtime-datascience-deps",
    "odh-notebooks-meta-runtime-kale-deps",
    "odh-notebooks-meta-workbench-datascience-deps",
)

FLAVORS = ("cpu", "cuda", "rocm")
AIPCC_ALIGNMENT_CONSTRAINTS_FILENAME = ".aipcc-alignment.constraints.txt"

# Target architectures per flavor, matching what each RH index provides.
# Used for `required-environments` (fail at lock time if wheels are missing for an arch,
# instead of discovering it during the container build — RHAIENG-5451 / RHAIENG-7088).
FLAVOR_MACHINES: dict[str, list[str]] = {
    "cpu": ["x86_64", "aarch64", "ppc64le", "s390x"],
    "cuda": ["x86_64", "aarch64"],
    "rocm": ["x86_64"],
}

# Baseline public-index images inherit direct dependency lock versions from paired
# AIPCC-index image requirements files.
BASELINE_AIPCC_ALIGNMENT_PAIRS: dict[Path, Path] = {
    Path("codeserver-baseline/ubi9-python-3.12"): Path("codeserver/ubi9-python-3.12"),
    Path("jupyter/baseline/ubi9-python-3.12"): Path("jupyter/datascience/ubi9-python-3.12"),
    Path("runtimes/baseline/ubi9-python-3.12"): Path("runtimes/datascience/ubi9-python-3.12"),
}

# Name aliases when package names differ between source (AIPCC) and target (baseline) indexes.
# key=baseline package name, value=source package name.
BASELINE_AIPCC_ALIGNMENT_SOURCE_ALIASES: dict[str, str] = {
    "pandoc": "pandoc-rhai",
}

# Optimal concurrency is 5-6 based on benchmarks (macOS 12-core, RH PyPI index with
# no HTTP cache headers).  Each uv process internally uses UV_CONCURRENT_DOWNLOADS
# (default 50) connections and UV_CONCURRENT_BUILDS (default cpu_count) build workers.
# The outer parallelism gains come from overlapping one solver's CPU time with another's
# network wait.  Repeated measurements (5-6 reps per value) show:
#   n=5: mean 107s, std 6s   — indistinguishable from n=6
#   n=6: mean 107s, std 7s   — best / current default
#   n=7: mean 119s, std 17s  — worse mean AND variance doubles
#   n=8: mean 113s, std 11s  — worse than n=6
# The variance spike at n=7 is the key signal: higher worker counts introduce
# scheduling jitter without reducing wall time.
MAX_WORKERS = 6


class IndexMode(StrEnum):
    auto = "auto"
    rh_index = "rh-index"
    public_index = "public-index"


# endregion


# region LogBuffer
BLUE = "\033[1;34m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"


@dataclass
class LogBuffer:
    """Simple logger that either prints immediately or buffers for grouped output.

    Use ``buffered=False`` in the main thread for immediate feedback,
    and ``buffered=True`` in worker threads so their output doesn't interleave.
    """

    buffered: bool = True
    _lines: list[str] = field(default_factory=list)

    def _emit(self, msg: str) -> None:
        if self.buffered:
            self._lines.append(msg)
        else:
            print(msg, flush=True)

    def info(self, msg: str) -> None:
        self._emit(f"🔹 {BLUE}{msg}{RESET}")

    def warning(self, msg: str) -> None:
        """ruff dislikes log.warn()"""
        self._emit(f"⚠️ {YELLOW}{msg}{RESET}")

    def error(self, msg: str) -> None:
        if self.buffered:
            self._lines.append(f"❌ {RED}{msg}{RESET}")
        else:
            print(f"❌ {RED}{msg}{RESET}", file=sys.stderr)

    def ok(self, msg: str) -> None:
        self._emit(f"✅ {GREEN}{msg}{RESET}")

    def print(self, msg: str) -> None:
        self._emit(msg)

    def flush(self) -> None:
        if self._lines:
            sys.stdout.write("\n".join(self._lines) + "\n")
            sys.stdout.flush()
            self._lines.clear()


# endregion


# region Helpers
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


def check_uv(log: LogBuffer) -> None:
    """Verify the uv wrapper exists and meets the minimum version requirement."""
    if not UV.is_file() or not os.access(UV, os.X_OK):
        log.error(f"Expected uv wrapper at '{UV}' but it is missing or not executable.")
        raise SystemExit(1)

    result = subprocess.run(
        [str(UV), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = result.stdout.strip().split()
    version_str = parts[1] if len(parts) >= 2 else "0.0.0"

    version_tuple = tuple(int(x) for x in version_str.split("."))
    if version_tuple < UV_MIN_VERSION:
        min_ver = ".".join(str(x) for x in UV_MIN_VERSION)
        log.error(f"uv version {version_str} found, but >= {min_ver} is required.")
        log.error("Please upgrade uv: https://github.com/astral-sh/uv")
        raise SystemExit(1)


def discover_all_image_project_dirs() -> list[Path]:
    """All image project directories under MAIN_DIRS (each contains pyproject.toml)."""
    dirs: set[Path] = set()
    for base_name in MAIN_DIRS:
        base = ROOT_DIR / base_name
        if base.is_dir():
            dirs.update(p.parent for p in base.rglob("pyproject.toml") if extract_python_version(p.parent) is not None)
    return sorted(dirs)


def find_target_dirs(target_dir: Path | None, log: LogBuffer) -> list[Path]:
    """Find directories containing pyproject.toml."""
    if target_dir is not None:
        candidate = target_dir if target_dir.is_absolute() else ROOT_DIR / target_dir
        if not candidate.is_dir() or not (candidate / "pyproject.toml").is_file():
            log.error(f"Target directory must exist and contain pyproject.toml: {candidate}")
            raise SystemExit(1)
        return [candidate]

    log.info("Scanning main directories for Python projects...")
    return discover_all_image_project_dirs()


def _list_changed_files(from_ref: str, to_ref: str = "HEAD") -> list[str]:
    """PR file diff via ci/cached-builds helper (symlink-aware three-dot diff)."""
    cached_builds = ROOT_DIR / "ci" / "cached-builds"
    if str(cached_builds) not in sys.path:
        sys.path.insert(0, str(cached_builds))
    import gha_pr_changed_files  # ruff: ignore[import-outside-top-level]

    return gha_pr_changed_files.list_changed_files(from_ref, to_ref)


def _path_under(path: Path, prefix: Path) -> bool:
    return path.is_relative_to(prefix)


def image_project_dir_for_repo_file(
    repo_relative: str,
    project_dirs: list[Path] | None = None,
) -> Path | None:
    """Map a repo-relative file path to its image project directory, if any."""
    path = Path(repo_relative)
    dirs = project_dirs if project_dirs is not None else discover_all_image_project_dirs()
    matches = [
        project_dir
        for project_dir in dirs
        if path == (rel := project_dir.relative_to(ROOT_DIR)) or _path_under(path, rel)
    ]
    if not matches:
        return None
    return max(matches, key=lambda project_dir: len(project_dir.parts))


def _is_global_lock_input(changed_path: str) -> bool:
    normalized = changed_path.replace("\\", "/")
    for global_path in GLOBAL_LOCK_INPUTS:
        entry = global_path.as_posix()
        if normalized == entry or normalized.startswith(f"{entry}/"):
            return True
    return False


def _is_lock_chain_file(relative_to_project: Path) -> bool:
    if relative_to_project.name in ("pyproject.toml", "pylock.toml"):
        return True
    if relative_to_project.name.startswith("requirements.") and relative_to_project.suffix == ".txt":
        return True
    return bool(relative_to_project.parts) and relative_to_project.parts[0] == "uv.lock.d"


def resolve_pr_scoped_target_dirs(
    pr_base: str,
    log: LogBuffer,
    *,
    pr_to_ref: str = "HEAD",
) -> list[Path]:
    """Image project dirs whose lock chain changed in the PR, or all dirs if global inputs changed.

    ``pr_base`` and ``pr_to_ref`` form a three-dot PR diff (``pr_base...pr_to_ref``). CI passes
    ``origin/<base-branch>`` and the fetched PR branch name; locally use ``origin/main`` and ``HEAD``.
    """
    log.info(f"PR lock scoping from {pr_base}...{pr_to_ref}")
    changed = _list_changed_files(pr_base, pr_to_ref)
    all_dirs = discover_all_image_project_dirs()

    if any(_is_global_lock_input(path) for path in changed):
        log.info("Global lock input changed in PR; regenerating all image project locks.")
        return all_dirs

    touched: set[Path] = set()
    for repo_relative in changed:
        project_dir = image_project_dir_for_repo_file(repo_relative, all_dirs)
        if project_dir is None:
            continue
        inner = Path(repo_relative).relative_to(project_dir.relative_to(ROOT_DIR))
        if _is_lock_chain_file(inner):
            touched.add(project_dir)

    if not touched:
        log.info("No image lock-chain changes in PR; skipping pylocks regeneration.")
        return []

    log.info(f"PR lock-chain changes in {len(touched)} project director(ies).")
    return sorted(touched)


def effective_index_mode(project_dir: Path, index_mode: IndexMode) -> IndexMode:
    """Resolve auto mode from lock layout: uv.lock.d/ → rh-index, else public-index."""
    if index_mode == IndexMode.auto:
        return IndexMode.rh_index if (project_dir / "uv.lock.d").is_dir() else IndexMode.public_index
    return index_mode


def detect_flavors(project_dir: Path) -> set[str]:
    """Detect available Dockerfile.konflux.* flavors (cpu, cuda, rocm) in a directory."""
    return {f for f in FLAVORS if (project_dir / f"Dockerfile.konflux.{f}").is_file()}


def extract_python_version(project_dir: Path) -> str | None:
    """Extract Python version from directory name suffix (e.g. ubi9-python-3.12 -> 3.12)."""
    name = project_dir.resolve().name
    # The version is everything after the last hyphen
    version = name.rsplit("-", maxsplit=1)[-1]
    if re.fullmatch(r"\d+\.\d+", version):
        return version
    return None


def ensure_json_format_param(url: str) -> str:
    """Append ``?format=json`` to a URL if not already present.

    Works around AIPCC-12921: Pulp's Simple API ignores Accept header quality
    values and returns HTML whenever ``text/html`` appears in the header.  The
    ``?format=json`` query parameter forces DRF to return PEP 691 JSON via its
    ``URL_FORMAT_OVERRIDE`` mechanism, bypassing content negotiation entirely.

    >>> ensure_json_format_param("https://example.com/simple/")
    'https://example.com/simple/?format=json'
    >>> ensure_json_format_param("https://example.com/simple/?format=json")
    'https://example.com/simple/?format=json'
    >>> ensure_json_format_param("https://example.com/simple/?other=1")
    'https://example.com/simple/?other=1&format=json'
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["format"] = ["json"]
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


_EXCLUDE_NEWER_HEADER_RE = re.compile(r"--exclude-newer(?:=|\s+)(\S+)")


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 with Z suffix (uv --exclude-newer)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_exclude_newer_from_lockfile(path: Path) -> str | None:
    """Read ``--exclude-newer`` from uv's autogenerated header comment, if present."""
    if not path.is_file():
        return None
    try:
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:8]
    except OSError:
        return None
    for line in head:
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        if "uv pip compile" not in stripped:
            continue
        m = _EXCLUDE_NEWER_HEADER_RE.search(stripped)
        if m:
            return m.group(1)
    return None


def resolve_exclude_newer(
    lockfile: Path,
    *,
    ci_check: bool,
    live_timestamp: str,
) -> str:
    """Choose ``--exclude-newer`` cutoff: pinned from file in CI check mode, else live."""
    if not ci_check:
        return live_timestamp
    parsed = parse_exclude_newer_from_lockfile(lockfile)
    return parsed if parsed is not None else live_timestamp


def _parse_pinned_requirements(requirements_file: Path) -> dict[str, str]:
    """Parse package==version entries from requirements.<flavor>.txt."""
    pinned: dict[str, str] = {}
    pattern = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^ ;\\]+)")
    for line in requirements_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "--")):
            continue
        match = pattern.match(stripped)
        if match is None:
            continue
        name = packaging.utils.canonicalize_name(match.group(1))
        pinned[name] = match.group(2)
    return pinned


def _project_direct_dependencies(pyproject_file: Path) -> dict[str, str]:
    """Return direct dependencies from pyproject keyed by canonical package name."""
    document = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))
    deps: dict[str, str] = {}
    for dep in document.get("project", {}).get("dependencies", []):
        req = packaging.requirements.Requirement(dep)
        deps[packaging.utils.canonicalize_name(req.name)] = req.name
    return deps


def generate_baseline_alignment_constraints(project_dir: Path, log: LogBuffer) -> Path | None:
    """Generate baseline-to-AIPCC direct-dependency alignment constraints file.

    Returns the generated constraints file path, or None if no pair applies.
    """
    try:
        rel = project_dir.relative_to(ROOT_DIR)
    except ValueError:
        # Unit tests may use temporary directories outside the repository tree.
        return None
    source_rel = BASELINE_AIPCC_ALIGNMENT_PAIRS.get(rel)
    if source_rel is None:
        return None

    source_requirements = ROOT_DIR / source_rel / "requirements.cpu.txt"
    if not source_requirements.is_file():
        log.warning(
            f"Alignment source requirements file not found: {source_requirements}. "
            "Skipping baseline AIPCC alignment for this directory."
        )
        return None

    pyproject_file = project_dir / "pyproject.toml"
    direct_deps = _project_direct_dependencies(pyproject_file)
    source_locked = _parse_pinned_requirements(source_requirements)

    generated: list[str] = []
    for canonical_name, original_name in sorted(direct_deps.items()):
        source_name = BASELINE_AIPCC_ALIGNMENT_SOURCE_ALIASES.get(canonical_name, canonical_name)
        source_version = source_locked.get(source_name)
        if source_version is None:
            continue
        generated.append(f"{original_name}=={source_version}")

    header = [
        "# Auto-generated by scripts/pylocks_generator.py",
        f"# Source pair: {source_rel.as_posix()} -> {rel.as_posix()}",
        "# Direct dependencies only; pyproject.toml remains version-agnostic.",
        "",
    ]
    content = "\n".join(header + generated) + "\n"
    # Repo-relative path so uv's pylock.toml header is identical on macOS and Linux CI.
    alignment_file = project_dir / AIPCC_ALIGNMENT_CONSTRAINTS_FILENAME
    alignment_file.write_text(content, encoding="utf-8")
    log.print(f"  🔗 Generated AIPCC alignment constraints: {alignment_file}")
    return alignment_file


# endregion


# region Lock generation
def get_rh_index_conf_file(project_dir: Path, flavor: str) -> Path:
    return project_dir / "build-args" / f"konflux.{flavor}.conf"


def resolve_rh_index_config(
    project_dir: Path,
    flavor: str,
    log: LogBuffer,
) -> ResolvedIndexConfig | None:
    conf_file = get_rh_index_conf_file(project_dir, flavor)
    try:
        return resolve_index_config(conf_file, require_konflux=True)
    except IndexResolutionError as exc:
        log.warning(str(exc))
        return None


def get_index_flags(project_dir: Path, flavor: str, log: LogBuffer) -> list[str] | None:
    """Build uv index flags from build-args/konflux.<flavor>.conf.

    Returns None on failure.
    """
    resolved = resolve_rh_index_config(project_dir, flavor, log)
    if resolved is None:
        return None

    return [f"--default-index={ensure_json_format_param(resolved.index_url)}"]


def lock_extra_index_flags_from_env() -> list[str]:
    """Extra ``--index=`` flags for ``uv pip compile`` only.

    ``UV_EXTRA_INDEX_URL`` / ``PIP_EXTRA_INDEX_URL`` must **not** be set while running
    ``uv run`` at the repo root: they make uv prefer RH indexes for *all* packages
    (e.g. ``uv``) and break macOS lock generation. The Makefile copies them into
    ``UV_LOCK_EXTRA_INDEX_URL`` / ``PIP_LOCK_EXTRA_INDEX_URL`` and unsets the originals.
    """
    seen: set[str] = set()
    flags: list[str] = []
    for key in ("UV_LOCK_EXTRA_INDEX_URL", "PIP_LOCK_EXTRA_INDEX_URL"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        for part in re.split(r"[\s,]+", raw):
            url = part.strip()
            if not url or url in seen:
                continue
            seen.add(url)
            flags.append(f"--index={ensure_json_format_param(url)}")
    return flags


def _replace_or_insert_toml_array(text: str, key: str, values: list[str]) -> str:
    """Replace an existing TOML array or insert it after ``[tool.uv]``."""
    items = ",\n".join(f'    "{v}"' for v in values)
    block = f"{key} = [\n{items},\n]"
    pattern = re.compile(
        rf"^{re.escape(key)}\s*=\s*\[.*?^\]",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(block, text)
    if "\n[tool.uv]" in text:
        return text.replace("\n[tool.uv]", f"\n[tool.uv]\n{block}", 1)
    return text + f"\n[tool.uv]\n{block}\n"


@contextlib.contextmanager
def _patched_flavor_environments(pyproject_path: Path, flavor: str):
    """Temporarily inject per-flavor ``required-environments`` into pyproject.toml.

    ``required-environments`` is a project-only setting (no CLI flag, no uv.toml support),
    so we patch the file on disk before ``uv pip compile`` and restore it afterward.
    It validates that wheels exist for every target architecture at lock time — without
    it, ``uv pip compile --universal`` silently accepts a version missing wheels for an
    architecture the `environments` marker doesn't distinguish (RHAIENG-7088).
    """
    machines = FLAVOR_MACHINES.get(flavor)
    if not machines or not pyproject_path.is_file():
        yield
        return
    original = pyproject_path.read_bytes()
    try:
        required_envs = [f"sys_platform == 'linux' and platform_machine == '{machine}'" for machine in machines]

        text = original.decode()
        text = _replace_or_insert_toml_array(text, "required-environments", required_envs)
        pyproject_path.write_text(text)
        yield
    finally:
        pyproject_path.write_bytes(original)


def run_lock(
    project_dir: Path,
    flavor: str,
    index_flags: list[str],
    mode: IndexMode,
    python_version: str,
    upgrade: bool,
    ci_check: bool,
    live_timestamp: str,
    log: LogBuffer,
    extra_constraints: Path | None = None,
) -> bool:
    """Run uv pip compile to generate a lock file. Returns True on success."""
    if mode == IndexMode.public_index:
        output = "pylock.toml"
        desc = "pylock.toml (public index)"
        log.print("➡️ Generating pylock.toml from public PyPI index...")
    else:
        (project_dir / "uv.lock.d").mkdir(exist_ok=True)
        output = f"uv.lock.d/pylock.{flavor}.toml"
        desc = f"{flavor.upper()} lock file"
        log.print(f"➡️ Generating {flavor.upper()} lock file...")

    # --universal generates a multi-arch pylock.  uv 0.10.5+ (#18081) filters wheels by
    # requires-python and marker disjointness even in --universal mode.  Combined with the
    # `environments` setting in each pyproject.toml (Linux + CPython, no platform_machine
    # axis), a package version missing wheels for one architecture is *not* rejected on
    # its own — `required-environments` below (RHAIENG-7088) is what actually enforces
    # per-architecture wheel coverage at lock-generation time.
    #
    # --python-platform linux is an alias for x86_64-unknown-linux-gnu and cannot produce
    # multi-arch output, so --universal is the correct choice.
    # Future: switch to uv.lock when https://github.com/astral-sh/uv/issues/6830 is resolved.
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

    # Use relative paths to avoid absolute paths in pylock.toml headers
    relative_constraints = os.path.relpath(CONSTRAINTS_FILE, project_dir)
    relative_overrides = os.path.relpath(OVERRIDES_FILE, project_dir)
    cmd.extend(["--constraints", relative_constraints, "--override", relative_overrides])
    if extra_constraints is not None:
        cmd.extend(["--constraints", os.path.relpath(extra_constraints, project_dir)])

    lock_path = project_dir / output
    exclude_newer = resolve_exclude_newer(lock_path, ci_check=ci_check, live_timestamp=live_timestamp)
    cmd.append(f"--exclude-newer={exclude_newer}")

    cmd.extend(index_flags)
    default_index = next(
        (flag.removeprefix("--default-index=") for flag in index_flags if flag.startswith("--default-index=")),
        None,
    )
    if default_index is not None:
        log.print(f"  🌐 Lock INDEX_URL: {default_index}")
    extra_idx = lock_extra_index_flags_from_env()
    if extra_idx:
        cmd.extend(extra_idx)
        log.print("  📎 Extra lock indexes from UV_LOCK_EXTRA_INDEX_URL / PIP_LOCK_EXTRA_INDEX_URL")

    compile_env = {k: v for k, v in os.environ.items() if k not in ("UV_EXTRA_INDEX_URL", "PIP_EXTRA_INDEX_URL")}

    pyproject_path = project_dir / "pyproject.toml"
    with _patched_flavor_environments(pyproject_path, flavor):
        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
                env=compile_env,
            )
        except subprocess.TimeoutExpired:
            log.warning(f"Timed out generating {desc} in {project_dir}")
            (project_dir / output).unlink(missing_ok=True)
            return False

    if result.stdout:
        log.print(result.stdout)
    if result.stderr:
        log.print(result.stderr)

    if result.returncode != 0:
        log.warning(f"Failed to generate {desc} in {project_dir}")
        (project_dir / output).unlink(missing_ok=True)
        return False

    log.ok(f"{desc} generated successfully.")
    return True


def generate_requirements_txt(
    project_dir: Path,
    flavor: str,
    log: LogBuffer,
    *,
    public_index: bool = False,
) -> bool:
    """Convert pylock → requirements.<flavor>.txt via helper script."""
    requirements_path = project_dir / f"requirements.{flavor}.txt"
    if public_index:
        pylock_path = project_dir / "pylock.toml"
        cmd = [sys.executable, str(PYLOCK_TO_REQUIREMENTS), str(pylock_path), str(requirements_path)]
    else:
        pylock_path = project_dir / "uv.lock.d" / f"pylock.{flavor}.toml"
        resolved = resolve_rh_index_config(project_dir, flavor, log)
        cmd = [sys.executable, str(PYLOCK_TO_REQUIREMENTS), str(pylock_path), str(requirements_path)]
        if resolved is None:
            log.warning(f"Falling back to --default-index recorded in {pylock_path} for requirements generation.")
        else:
            cmd.append(resolved.index_url)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.stdout:
        log.print(result.stdout.rstrip())
    if result.stderr:
        log.print(result.stderr.rstrip())
    if result.returncode != 0:
        log.warning(f"Failed to generate {requirements_path}")
        return False
    log.ok(f"requirements.{flavor}.txt generated.")
    return True


def process_directory(
    tdir: Path,
    index_mode: IndexMode,
    upgrade: bool,
    ci_check: bool,
    live_timestamp: str,
    requirements_only: bool = False,
) -> tuple[Path, bool, LogBuffer]:
    """Process one directory. Returns (path, success, log)."""
    log = LogBuffer(buffered=True)

    log.print("")
    log.print("=" * 67)
    log.info(f"Processing directory: {tdir}")
    log.print("=" * 67)

    python_version = extract_python_version(tdir)
    if python_version is None:
        log.warning(f"Skipping non-image pyproject.toml (not .../ubi9-python-X.Y): {tdir}")
        return tdir, True, log

    flavors = detect_flavors(tdir)
    if not flavors:
        log.warning(f"No Dockerfile.konflux.* files found in {tdir} (cpu/cuda/rocm). Skipping.")
        return tdir, False, log

    log.print(f"📦 Python version: {python_version}")
    log.print("🧩 Detected flavors:")
    for f in sorted(flavors):
        log.print(f"  • {f.upper()}")
    log.print("")

    effective_mode = effective_index_mode(tdir, index_mode)
    log.info(f"Effective mode for this directory: {effective_mode.value}")

    dir_success = True

    if effective_mode == IndexMode.public_index:
        extra_constraints = generate_baseline_alignment_constraints(tdir, log) if not requirements_only else None
        if requirements_only:
            pylock_path = tdir / "pylock.toml"
            if not pylock_path.is_file():
                log.warning(f"No {pylock_path} found, skipping public-index requirements.")
                dir_success = False
            elif not generate_requirements_txt(tdir, "cpu", log, public_index=True):
                dir_success = False
        else:
            try:
                if not run_lock(
                    tdir,
                    "cpu",
                    [PUBLIC_INDEX],
                    effective_mode,
                    python_version,
                    upgrade,
                    ci_check,
                    live_timestamp,
                    log,
                    extra_constraints,
                ):
                    dir_success = False
                elif not generate_requirements_txt(tdir, "cpu", log, public_index=True):
                    dir_success = False
            finally:
                if extra_constraints is not None:
                    extra_constraints.unlink(missing_ok=True)
    else:
        for flavor in ("cpu", "cuda", "rocm"):
            if flavor not in flavors:
                continue
            if requirements_only:
                pylock_path = tdir / "uv.lock.d" / f"pylock.{flavor}.toml"
                if not pylock_path.is_file():
                    log.warning(f"No {pylock_path} found, skipping {flavor}.")
                    dir_success = False
                    continue
                if not generate_requirements_txt(tdir, flavor, log):
                    dir_success = False
                continue
            flags = get_index_flags(tdir, flavor, log)
            if flags is None:
                dir_success = False
                continue
            if not run_lock(
                tdir,
                flavor,
                flags,
                effective_mode,
                python_version,
                upgrade,
                ci_check,
                live_timestamp,
                log,
            ):
                dir_success = False
            elif not generate_requirements_txt(tdir, flavor, log):
                dir_success = False

    return tdir, dir_success, log


# endregion


app = typer.Typer(add_completion=False)


@app.command()
def main(
    index_mode: Annotated[
        IndexMode, typer.Argument(help="Index mode: auto, rh-index, or public-index")
    ] = IndexMode.auto,
    target_dir: Annotated[Path | None, typer.Argument(help="Specific project directory to process")] = None,
    requirements_only: Annotated[
        bool,
        typer.Option(
            "--requirements-only",
            help="Only regenerate requirements.txt from existing pylock files, skip lock generation",
        ),
    ] = False,
    pr_base: Annotated[
        str | None,
        typer.Option(
            "--pr-base",
            help="Base ref for PR scoping (three-dot diff pr_base...pr_to_ref); CI uses origin/<base-branch>",
        ),
    ] = None,
    pr_to_ref: Annotated[
        str,
        typer.Option(
            "--pr-to-ref",
            help="Head ref for PR scoping (three-dot diff pr_base...pr_to_ref); CI uses fetched PR branch",
        ),
    ] = "HEAD",
) -> None:
    """Generate pylock.toml lock files for Python project directories."""
    log = LogBuffer(buffered=False)

    # PRE-FLIGHT
    if not requirements_only:
        check_uv(log)

    if requirements_only:
        log.info("--requirements-only: skipping lock generation, converting existing pylock files.")

    # UPGRADE FLAG
    upgrade = os.environ.get("FORCE_LOCKFILES_UPGRADE", "0") == "1"
    if upgrade and not requirements_only:
        log.info("FORCE_LOCKFILES_UPGRADE=1 detected. Will upgrade all packages to latest versions.")

    if not requirements_only:
        log.info(f"Using index mode: {index_mode.value}")

    ci_check = os.environ.get("PYLOCKS_CI_CHECK", "") == "1"
    live_ts = utc_now_iso()
    if ci_check and not requirements_only:
        log.info("PYLOCKS_CI_CHECK=1: using pinned --exclude-newer from each lockfile header when present.")

    # TARGET DIRECTORIES
    if pr_base is not None:
        if target_dir is not None:
            log.error("Cannot combine a specific target directory with --pr-base.")
            raise SystemExit(1)
        target_dirs = resolve_pr_scoped_target_dirs(pr_base, log, pr_to_ref=pr_to_ref)
        if not target_dirs:
            log.ok("Skipped pylocks regeneration.")
            return
    else:
        target_dirs = find_target_dirs(target_dir, log)
        if not target_dirs:
            log.error("No directories containing pyproject.toml were found.")
            raise SystemExit(1)

    # PARALLEL LOCK GENERATION
    success_dirs: list[Path] = []
    failed_dirs: list[Path] = []

    for tdir in target_dirs:
        flavor_names = ", ".join(f.upper() for f in sorted(detect_flavors(tdir)))
        log.info(f"Scheduled: {tdir} [{flavor_names}]")

    def _run(directory: Path) -> tuple[Path, bool, LogBuffer]:
        try:
            return process_directory(directory, index_mode, upgrade, ci_check, live_ts, requirements_only)
        except Exception as exc:
            err_log = LogBuffer(buffered=True)
            err_log.error(f"Unexpected error processing {directory}: {exc}")
            return directory, False, err_log

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_run, tdir): tdir for tdir in target_dirs}
        for future in as_completed(futures):
            tdir, success, dir_log = future.result()
            dir_log.flush()
            if success:
                success_dirs.append(tdir)
            else:
                failed_dirs.append(tdir)

    # SUMMARY
    log.print("")
    log.print("=" * 67)
    log.ok("Lock generation complete.")
    log.print("=" * 67)

    if success_dirs:
        log.ok("Successfully generated locks for:")
        for d in sorted(success_dirs):
            log.print(f"  • {d}")

    if failed_dirs:
        log.print("")
        log.warning("Failed lock generation for:")
        for d in sorted(failed_dirs):
            log.print(f"  • {d}")
            log.print(
                "Please comment out the missing package to continue and report the missing package to the RH index maintainers"
            )
        raise SystemExit(1)


if __name__ == "__main__":
    app()
