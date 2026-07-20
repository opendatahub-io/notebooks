#!/usr/bin/env python3
"""Extract PEP 517 build-system.requires transitively from sdists on PyPI.

For each pinned package in requirements.cpu.txt, downloads its sdist (if one
exists), reads the root pyproject.toml, and collects build-system.requires.
Then recursively resolves build deps of build deps until no new packages are
discovered.

Build backends often have empty build-system.requires (e.g. hatchling
self-bootstraps via backend-path) but still need their project.dependencies
installed when built/used from sdist. Those install deps can themselves be
sdists with their own build-system.requires (hatchling → trove-classifiers →
calver). So for every package discovered as a build dep, we also follow its
project.dependencies to continue the closure — still seeded only from the
runtime lockfile.

Arch-aware logging
------------------
Konflux builds linux/x86_64, aarch64, ppc64le, and s390x. For each package we
log which arches lack a usable Python 3.12 wheel (must build from sdist) vs
where a wheel exists. The emitted requirements-build.in is still the full
transitive closure — Hermeto may use an sdist even when a wheel exists, and a
single lockfile must cover every arch.

scikit-build-core
-----------------
When a project uses scikit-build-core, ``get_requires_for_build_wheel`` may
request the PyPI ``cmake`` / ``ninja`` packages even if they are absent from
``build-system.requires``. Defaults (scikit-build-core 1.x): ``cmake>=3.15``
(or the configured ``tool.scikit-build.cmake.version``) and ``ninja>=1.5``.
We synthesize those into the closure so Hermeto can prefetch them — hermetic
images typically lack system cmake/ninja/make.

PEP 508 markers
---------------
Markers are evaluated for Python 3.12 / Linux against each Konflux arch. A
dependency is included if its marker applies on *any* arch (union). Non-Linux
or wrong-Python markers (e.g. os_name == 'nt') remain excluded. Enqueue
resolves a version that satisfies the specifier. Paste output for
requirements-build.in keeps AND-merged version bounds for one Hermeto lockfile.

Usage:
    python3 extract-build-deps.py requirements.cpu.txt
"""

from __future__ import annotations

import io
import json
import re
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from dataclasses import dataclass, field

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

# Python 3.12 / Linux, one env per Konflux build arch (union for markers).
_TARGET_ENV_BASE = {
    "python_version": "3.12",
    "python_full_version": "3.12.0",
    "os_name": "posix",
    "sys_platform": "linux",
    "platform_system": "Linux",
    "implementation_name": "cpython",
    "implementation_version": "3.12.0",
}
TARGET_MACHINES = ("x86_64", "aarch64", "ppc64le", "s390x")
TARGET_ENVS = [
    {**_TARGET_ENV_BASE, "platform_machine": machine} for machine in TARGET_MACHINES
]

# Filename substrings that identify a wheel's architecture tag.
_MACHINE_IN_WHEEL = {
    "x86_64": ("x86_64", "amd64"),
    "aarch64": ("aarch64", "arm64"),
    "ppc64le": ("ppc64le",),
    "s390x": ("s390x",),
}

# Normalized name → /pypi/{name}/json payload (avoids a second metadata fetch
# when a package was just resolved for enqueue).
_pypi_project_cache: dict[str, dict] = {}


def fetch_pypi_project(name: str) -> dict | None:
    key = canonicalize_name(name)
    if key in _pypi_project_cache:
        return _pypi_project_cache[key]
    try:
        resp = urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: pypi {name}: {e}", file=sys.stderr)
        return None
    _pypi_project_cache[key] = data
    return data


def resolve_version(name: str, specifier: SpecifierSet) -> str | None:
    """Latest PyPI release of name that satisfies specifier (empty = any)."""
    data = fetch_pypi_project(name)
    if not data:
        return None
    matched: list[Version] = []
    for ver_str, files in data.get("releases", {}).items():
        if not files:
            continue
        try:
            ver = Version(ver_str)
        except InvalidVersion:
            continue
        if ver in specifier:
            matched.append(ver)
    if not matched:
        return None
    return str(max(matched))


def is_root_pyproject(path: str) -> bool:
    """Match only <sdist-root>/pyproject.toml, not nested fixtures/tests."""
    parts = path.replace("\\", "/").split("/")
    return path == "pyproject.toml" or (len(parts) == 2 and parts[1] == "pyproject.toml")


def _skbuild_version_req(tool_name: str, version: object, *, default: str) -> str | None:
    """Map tool.scikit-build.<tool>.version to a PEP 508 req, or default/None."""
    if version is True:
        return tool_name
    if version == "":
        return None  # explicitly disabled
    if isinstance(version, str) and re.match(r"^[\d<=>!~]", version):
        return (
            f"{tool_name}=={version}"
            if version[0].isdigit()
            else f"{tool_name}{version}"
        )
    # Unset, CMakeLists.txt, or other non-specifier → hermetic default.
    return default


def scikit_build_tool_requires(toml: dict) -> list[str]:
    """Synthesize cmake/ninja PyPI reqs matching scikit-build-core defaults.

    scikit-build-core's get_requires_for_build_wheel requests these even when
    they are not listed under build-system.requires (e.g. pyzmq sets only
    tool.scikit-build.cmake.version; ninja still defaults to >=1.5).
    """
    build_requires = toml.get("build-system", {}).get("requires") or []
    sb = toml.get("tool", {}).get("scikit-build")
    uses_skbuild = sb is not None or any(
        "scikit-build-core" in r.split(";")[0].lower() for r in build_requires
    )
    if not uses_skbuild:
        return []

    sb = sb if isinstance(sb, dict) else {}
    cmake_section = sb.get("cmake") if isinstance(sb.get("cmake"), dict) else {}
    ninja_section = sb.get("ninja") if isinstance(sb.get("ninja"), dict) else {}

    requires: list[str] = []
    cmake_req = _skbuild_version_req(
        "cmake", cmake_section.get("version"), default="cmake>=3.15"
    )
    if cmake_req:
        requires.append(cmake_req)
    ninja_req = _skbuild_version_req(
        "ninja", ninja_section.get("version"), default="ninja>=1.5"
    )
    if ninja_req:
        requires.append(ninja_req)
    return requires


def read_pyproject_meta(content: bytes) -> tuple[list[str], list[str]]:
    toml = tomllib.loads(content.decode())
    build_requires = list(toml.get("build-system", {}).get("requires") or [])
    build_requires.extend(scikit_build_tool_requires(toml))
    project_deps = toml.get("project", {}).get("dependencies") or []
    return build_requires, project_deps


# (name, version) → urls[] from project or versioned JSON.
_release_files_cache: dict[tuple[str, str], list[dict]] = {}
# (name, version) → /pypi/{name}/{version}/json payload (for requires_dist).
_version_json_cache: dict[tuple[str, str], dict] = {}


def fetch_version_json(name: str, version: str) -> dict | None:
    key = (canonicalize_name(name), version)
    if key in _version_json_cache:
        return _version_json_cache[key]
    try:
        resp = urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: {name}=={version}: {e}", file=sys.stderr)
        return None
    _version_json_cache[key] = data
    _release_files_cache[key] = data.get("urls", [])
    return data


def release_files(name: str, version: str) -> list[dict]:
    """PyPI file records (wheels + sdist) for name==version."""
    key = (canonicalize_name(name), version)
    if key in _release_files_cache:
        return _release_files_cache[key]

    project = fetch_pypi_project(name)
    if project and version in project.get("releases", {}):
        files = project["releases"][version]
        _release_files_cache[key] = files
        return files

    data = fetch_version_json(name, version)
    return data.get("urls", []) if data else []


def _wheel_matches_machine(filename: str, machine: str) -> bool:
    return any(token in filename for token in _MACHINE_IN_WHEEL[machine])


def wheel_usable_on(filename: str, machine: str) -> bool:
    """True if this wheel can install on CPython 3.12 for the given linux machine.

    Uses filename tag substrings (not packaging.tags) — same idea as the
    prefetch arch filter, plus cp312/abi3/py3-none handling.
    """
    name = filename.lower()
    if not name.endswith(".whl"):
        return False

    if "none-any" in name:
        return any(tag in name for tag in ("py3-", "py2.py3-"))

    # py3-none-<platform> (e.g. cmake embedding native binaries).
    if re.search(r"py(2\.)?3-none-", name):
        return _wheel_matches_machine(name, machine)

    if "cp312" not in name:
        abi3 = re.search(r"cp3(\d+)-abi3", name)
        if not (abi3 and int(abi3.group(1)) <= 12):
            return False

    return _wheel_matches_machine(name, machine)


def arches_needing_sdist(name: str, version: str) -> list[str]:
    """Target machines with no usable wheel for name==version (must build sdist)."""
    wheels = [f["filename"] for f in release_files(name, version) if f.get("packagetype") == "bdist_wheel"]
    return [m for m in TARGET_MACHINES if not any(wheel_usable_on(w, m) for w in wheels)]


def extract_sdist_meta(name: str, version: str) -> tuple[list[str], list[str]]:
    """Return (build-system.requires + scikit-build tools, project.dependencies)."""
    sdist_urls = [u for u in release_files(name, version) if u.get("packagetype") == "sdist"]
    if not sdist_urls:
        return [], []

    sdist_url = sdist_urls[0]["url"]
    sdist_filename = sdist_urls[0]["filename"]

    try:
        sdist_data = urllib.request.urlopen(sdist_url, timeout=30).read()
    except Exception as e:
        print(f"  WARN: download {name}=={version}: {e}", file=sys.stderr)
        return [], []

    try:
        if sdist_filename.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(sdist_data), mode="r:gz") as tf:
                for m in tf.getmembers():
                    if is_root_pyproject(m.name):
                        fobj = tf.extractfile(m)
                        if fobj:
                            return read_pyproject_meta(fobj.read())
        elif sdist_filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(sdist_data)) as zf:
                for zname in zf.namelist():
                    if is_root_pyproject(zname):
                        return read_pyproject_meta(zf.read(zname))
    except Exception as e:
        print(f"  WARN: parse {name}=={version}: {e}", file=sys.stderr)

    return [], []


def parse_requirements_file(path: str) -> dict[str, str]:
    packages: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" not in line:
                continue
            try:
                req = Requirement(line.split("\\")[0].strip())
            except Exception:
                continue
            for spec in req.specifier:
                if spec.operator == "==":
                    packages[canonicalize_name(req.name)] = spec.version
                    break
    return packages


def parse_req(req_str: str) -> Requirement | None:
    try:
        return Requirement(req_str)
    except Exception:
        return None


def marker_applies(req: Requirement) -> bool:
    """True if the requirement has no marker or it applies on any TARGET_ENVS arch."""
    if req.marker is None:
        return True
    for env in TARGET_ENVS:
        try:
            if req.marker.evaluate(env):
                return True
        except Exception:
            return True
    return False


def compact_specifier(spec: SpecifierSet) -> SpecifierSet:
    """Collapse redundant lower/upper bounds into an equivalent SpecifierSet."""
    if not spec:
        return spec

    lower: tuple[str, Version] | None = None  # (>= or >)
    upper: tuple[str, Version] | None = None  # (<= or <)
    others: list[str] = []

    for clause in spec:
        op, ver = clause.operator, Version(clause.version)
        if op in (">=", ">"):
            if lower is None or ver > lower[1] or (ver == lower[1] and op == ">"):
                lower = (op, ver)
        elif op in ("<=", "<"):
            if upper is None or ver < upper[1] or (ver == upper[1] and op == "<"):
                upper = (op, ver)
        else:
            others.append(f"{op}{clause.version}")

    parts: list[str] = []
    if lower:
        parts.append(f"{lower[0]}{lower[1]}")
    if upper:
        parts.append(f"{upper[0]}{upper[1]}")
    parts.extend(others)
    return SpecifierSet(",".join(parts))


@dataclass
class BuildDepConstraint:
    """Accumulated PEP 508 constraint for one build-dep package."""

    extras: set[str] = field(default_factory=set)
    specifier: SpecifierSet = field(default_factory=SpecifierSet)
    conflict: bool = False

    def merge(self, req: Requirement) -> None:
        """AND-merge req. On unsatisfiable intersection, fall back to bare name."""
        self.extras.update(req.extras)
        if self.conflict:
            return
        name = canonicalize_name(req.name)
        merged_spec = self.specifier & req.specifier
        if resolve_version(name, merged_spec) is None:
            print(
                f"  WARN: conflict merging {req} into {name}{self.specifier}; "
                f"emitting bare {name}",
                file=sys.stderr,
            )
            self.conflict = True
            self.specifier = SpecifierSet()
            return
        self.specifier = merged_spec

    def as_requirement(self, name: str) -> str:
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        if self.conflict or not self.specifier:
            return f"{name}{extras}"
        return f"{name}{extras}{compact_specifier(self.specifier)}"


def enqueue_new(
    req: Requirement,
    seen_versions: set[tuple[str, str]],
    next_round: list[tuple[str, str]],
    *,
    kind: str,
) -> None:
    name = canonicalize_name(req.name)
    version = resolve_version(name, req.specifier)
    if not version:
        print(
            f"  WARN: no PyPI version for {req}",
            file=sys.stderr,
        )
        return
    key = (name, version)
    if key in seen_versions:
        return
    seen_versions.add(key)
    next_round.append((name, version))
    print(f"    -> {kind}: {name}=={version} (from {req})")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} requirements.cpu.txt", file=sys.stderr)
        sys.exit(1)

    runtime_pinned = parse_requirements_file(sys.argv[1])
    to_process: list[tuple[str, str]] = list(runtime_pinned.items())
    # Track name==version so conflicting upper/lower bounds can each be scanned.
    seen_versions: set[tuple[str, str]] = set(runtime_pinned.items())
    build_deps: dict[str, BuildDepConstraint] = {}

    iteration = 0
    while to_process:
        iteration += 1
        next_round: list[tuple[str, str]] = []
        print(f"\n=== Iteration {iteration}: processing {len(to_process)} packages ===")

        for name, version in to_process:
            needing = arches_needing_sdist(name, version)
            is_build_package = name not in runtime_pinned

            if needing:
                have = [m for m in TARGET_MACHINES if m not in needing]
                print(
                    f"  {name}=={version}: sdist needed on {','.join(needing)}"
                    + (f" (wheels on {','.join(have)})" if have else " (no wheels)")
                )
            else:
                print(
                    f"  {name}=={version}: wheel on all arches "
                    f"({','.join(TARGET_MACHINES)})"
                )

            # Always collect build-system.requires (+ scikit-build tools) for the
            # full transitive closure — do not omit packages that have wheels.
            build_requires, project_deps = extract_sdist_meta(name, version)

            if build_requires:
                print(f"  {name}=={version} build requires: {build_requires}")

            for req_str in build_requires:
                req = parse_req(req_str)
                if req is None or not marker_applies(req):
                    continue
                dep_name = canonicalize_name(req.name)
                build_deps.setdefault(dep_name, BuildDepConstraint()).merge(req)
                enqueue_new(req, seen_versions, next_round, kind="new build dep")

            if is_build_package and project_deps:
                print(f"  {name}=={version} project.dependencies: {project_deps}")
                for req_str in project_deps:
                    req = parse_req(req_str)
                    if req is None or not marker_applies(req):
                        continue
                    enqueue_new(
                        req, seen_versions, next_round, kind="build-backend install dep"
                    )

        to_process = next_round

    print(f"\n=== Unique build dep requirements ({len(build_deps)}) ===")
    print("# Paste into requirements-build.in:")
    for dep_name in sorted(build_deps):
        print(build_deps[dep_name].as_requirement(dep_name))


if __name__ == "__main__":
    main()
