"""Refresh ``notebook-python-dependencies`` (and Python stack in ``notebook-software``) from pylock files at git commits recorded in commit env files.

For each workbench ImageStream tag, resolves the git tree-ish as:

- Latest tag (suffix ``-n``): versions are taken from the **working tree** lockfile first (same files
  ``make test`` uses: ``uv.lock.d/pylock.<cpu|cuda|rocm>.toml`` or ``pylock.toml``). That matches local
  ``pylock.toml`` pins. If no file exists on disk, the SHA from ``commit-latest.env`` is used with
  ``git show`` (fetching from the canonical repo if needed): ``https://github.com/opendatahub-io/notebooks.git``
  (``--variant odh``) or ``https://github.com/red-hat-data-services/notebooks.git`` (``--variant rhoai``).
- Older tags (e.g. ``-2025-2``): SHA from ``commit.env`` (``<base>-commit-2025-2``).

Those SHAs match ``manifests/tools/generate_kustomization.py`` / ConfigMap keys.

Dependency *names* and ordering are taken from the existing manifest; versions are updated from
the resolved lockfile at each ref (same translation rules as ``tests/test_main.py``). Older commits may only have ``requirements.txt`` or flavor files such as ``requirements.cpu.txt``
instead of ``pylock.toml`` / ``uv.lock.d/pylock.*.toml``; those are parsed as pinned PEP 508 requirements.
Image directories are discovered via ``pyproject.toml`` or those requirements files at the
``<os>-python-<ver>/`` root. If that Python version exists only in git history, the path is derived
from a sibling on-disk tree so ``git show <sha>:…`` can load lockfiles.

JSON annotations are written as YAML literal blocks (``|``) with the same bracket layout as
``opendatahub-io`` / ``mtchoum1`` ImageStreams: opening ``[`` on the first line of the block, two
spaces before each ``{...}`` line, closing ``]`` aligned with ``[`` — see e.g.
https://github.com/mtchoum1/notebooks/blob/main/manifests/odh/base/jupyter-datascience-notebook-imagestream.yaml
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import packaging.markers
import packaging.version
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manifests.tools.commit_env_refs import parse_env_file  # noqa: E402
from manifests.tools.generate_kustomization import Workbench, discover_config  # noqa: E402
from manifests.tools.package_names import manifest_name_to_pip  # noqa: E402
from tests.manifests import (  # noqa: E402
    extract_metadata_from_path,
    get_source_of_truth_filepath,
)

logger = logging.getLogger(__name__)

# Force accelerator flavor when resolving ImageStream paths. ``extract_metadata_from_path`` may
# infer "cuda" from Dockerfile.cuda even for the CPU ImageStream (same tree builds both), and
# RStudio ImageStreams are not represented in ``get_source_of_truth_filepath`` (buildconfig-only).
_ACCELERATOR_OVERRIDE_FOR_RESOURCE: dict[str, str | None] = {
    "jupyter-minimal-notebook-imagestream.yaml": None,
    "jupyter-minimal-gpu-notebook-imagestream.yaml": "cuda",
    "jupyter-datascience-notebook-imagestream.yaml": None,
    "jupyter-pytorch-notebook-imagestream.yaml": "cuda",
    "jupyter-tensorflow-notebook-imagestream.yaml": "cuda",
    "jupyter-trustyai-notebook-imagestream.yaml": None,
    "code-server-notebook-imagestream.yaml": None,
    "jupyter-rocm-minimal-notebook-imagestream.yaml": "rocm",
    "jupyter-rocm-pytorch-notebook-imagestream.yaml": "rocm",
    "jupyter-rocm-tensorflow-notebook-imagestream.yaml": "rocm",
    "jupyter-pytorch-llmcompressor-imagestream.yaml": "cuda",
}

_RSTUDIO_NOTEBOOK_RESOURCES = frozenset(
    {
        "rstudio-notebook-imagestream.yaml",
        "rstudio-gpu-notebook-imagestream.yaml",
    }
)

# Canonical Git URLs for ``git fetch`` when the ``-n`` tag commit is not already in the local object DB.
_CANONICAL_REPO_URL: dict[str, str] = {
    "odh": "https://github.com/opendatahub-io/notebooks.git",
    "rhoai": "https://github.com/red-hat-data-services/notebooks.git",
}

# Commit values from *.env must look like hex object IDs before passing to git (avoid ref injection).
# Repo env files use short SHAs (7+ chars); full 40-char hashes are also accepted.
_GIT_HEX_OBJECT_ID = re.compile(r"^[0-9a-f]{7,40}$")


def _is_under_jupyter_rocm_tree(directory: Path) -> bool:
    parts = directory.parts
    try:
        j = parts.index("jupyter")
    except ValueError:
        return False
    return len(parts) > j + 1 and parts[j + 1] == "rocm"


def _is_under_jupyter_minimal_tree(directory: Path) -> bool:
    """``jupyter/minimal/<os>-python-*/`` (ROCm minimal uses the same tree as CPU; lockfile is ``pylock.rocm.toml``)."""
    parts = directory.parts
    try:
        j = parts.index("jupyter")
    except ValueError:
        return False
    return len(parts) > j + 1 and parts[j + 1] == "minimal"


def _workbench_dir_consistent_with_rocm_policy(wb: Workbench, directory: Path) -> bool:
    """Skip ``jupyter/rocm/...`` source trees when the ImageStream is not a ROCm workbench."""
    rf = wb.resource_file
    rocm_tree = _is_under_jupyter_rocm_tree(directory)

    # ROCm minimal ImageStream is built from jupyter/minimal/..., not jupyter/rocm/minimal/...
    if rf == "jupyter-rocm-minimal-notebook-imagestream.yaml":
        return _is_under_jupyter_minimal_tree(directory)

    if rf.startswith("jupyter-rocm-"):
        return rocm_tree
    if rf.startswith("jupyter-") and rocm_tree:
        return False
    return True


def _is_image_directory(directory: Path) -> bool:
    try:
        _ubi, _lang, _python = directory.name.split("-")
    except ValueError:
        return False
    else:
        return True


def _manifests_variant_dir(variant: str) -> Path:
    return ROOT / "manifests" / variant


def _discover_candidate_dirs() -> list[Path]:
    """Discover ``<os>-python-<ver>/`` trees via ``pyproject.toml`` or requirements lockfiles.

    Marker filenames match what :func:`pylock_candidate_rel_paths` may read (no unrelated
    ``requirements.*.txt`` such as dev/build-only files).
    """
    marker_names = (
        "pyproject.toml",
        "requirements.txt",
        "requirements.cpu.txt",
        "requirements.cuda.txt",
        "requirements.rocm.txt",
    )
    roots = ("jupyter", "codeserver", "rstudio")
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        for name in marker_names:
            for marker in ROOT.glob(f"{root}/**/{name}"):
                d = marker.parent
                if not _is_image_directory(d):
                    continue
                key = d.resolve()
                if key in seen:
                    continue
                seen.add(key)
                out.append(d)
    return out


def _dirs_for_workbench(manifests_dir: Path, wb: Workbench, candidate_dirs: list[Path]) -> list[Path]:
    target = (manifests_dir / "base" / wb.resource_file).resolve()
    if wb.resource_file in _RSTUDIO_NOTEBOOK_RESOURCES:
        return [d for d in candidate_dirs if "rstudio" in d.parts]

    found: list[Path] = []
    for d in candidate_dirs:
        if not _workbench_dir_consistent_with_rocm_policy(wb, d):
            continue
        try:
            meta = extract_metadata_from_path(d)
            if wb.resource_file in _ACCELERATOR_OVERRIDE_FOR_RESOURCE:
                meta = dataclasses.replace(
                    meta,
                    accelerator_flavor=_ACCELERATOR_OVERRIDE_FOR_RESOURCE[wb.resource_file],
                )
            truth = get_source_of_truth_filepath(manifests_dir, meta)
        except ValueError:
            continue
        if truth.resolve() == target:
            found.append(d)
    return found


def notebook_dirname_from_base_key(base_key: str) -> str | None:
    """Return ``<os>-python-<major.minor>`` when ``base_key`` encodes it (e.g. ``...-py311-ubi9``)."""
    m_os = re.search(r"-py(\d)(\d+)-([^-]+)(?:$|-)", base_key)
    if not m_os:
        return None
    py = f"{m_os.group(1)}.{m_os.group(2)}"
    return f"{m_os.group(3)}-python-{py}"


def pick_notebook_dir_for_base_key(candidates: list[Path], base_key: str) -> Path | None:
    """Return an on-disk notebook tree path when it exists for this tag's Python/OS."""
    if not candidates:
        return None

    want = notebook_dirname_from_base_key(base_key)
    if want is not None:
        for d in candidates:
            if d.name == want:
                return d
        return None

    m = re.search(r"-py(\d)(\d+)-", base_key)
    if m:
        py = f"{m.group(1)}.{m.group(2)}"
        matching = [d for d in candidates if f"python-{py}" in d.name]
        if len(matching) == 1:
            return matching[0]
        if len(matching) > 1:
            return None
        return None

    return candidates[0] if len(candidates) == 1 else None


def resolve_notebook_directory(candidates: list[Path], base_key: str) -> Path | None:
    """Resolve the notebook tree path for lockfile lookup (worktree or ``git show``).

    Prefer an on-disk ``<os>-python-<ver>/`` directory. If it is missing locally but another Python
    tree exists for the same ImageStream (e.g. only ``3.12`` on disk, tag is ``py311``), synthesize
    ``…/<os>-python-3.11/`` from a sibling's parent so ``git show <commit>:jupyter/.../ubi9-python-3.11/…``
    can still succeed.
    """
    if not candidates:
        return None
    picked = pick_notebook_dir_for_base_key(candidates, base_key)
    if picked is not None:
        return picked
    want = notebook_dirname_from_base_key(base_key)
    if want is None:
        return None
    os_prefix, _, _ = want.partition("-python-")
    if os_prefix:
        for d in candidates:
            if d.name.startswith(f"{os_prefix}-python-"):
                return d.with_name(want)
        return None
    return candidates[0].with_name(want)


def _pylock_kind_from_tag(wb_resource_file: str, base_key: str) -> str:
    if "-rocm-" in base_key or "jupyter-rocm-" in wb_resource_file:
        return "rocm"
    if wb_resource_file in _RSTUDIO_NOTEBOOK_RESOURCES:
        if "gpu" in wb_resource_file or "-cuda-" in base_key:
            return "cuda"
        return "cpu"
    if "-cuda-" in base_key or "-minimal-cuda-" in base_key:
        return "cuda"
    if wb_resource_file in (
        "jupyter-minimal-gpu-notebook-imagestream.yaml",
        "jupyter-pytorch-notebook-imagestream.yaml",
        "jupyter-tensorflow-notebook-imagestream.yaml",
        "jupyter-pytorch-llmcompressor-imagestream.yaml",
    ):
        return "cuda"
    return "cpu"


def pylock_candidate_rel_paths(notebook_dir: Path, kind: str) -> list[str]:
    """Paths to try: pylock TOMLs, ``requirements.<kind>.txt``, then ``requirements.txt``."""
    rel_uv = notebook_dir / "uv.lock.d" / f"pylock.{kind}.toml"
    rel_legacy = notebook_dir / "pylock.toml"
    rel_req_kind = notebook_dir / f"requirements.{kind}.txt"
    rel_req = notebook_dir / "requirements.txt"
    out: list[str] = [
        str(rel_uv.relative_to(ROOT)),
        str(rel_legacy.relative_to(ROOT)),
        str(rel_req_kind.relative_to(ROOT)),
        str(rel_req.relative_to(ROOT)),
    ]
    seen: set[str] = set()
    deduped: list[str] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def _worktree_read_first_existing(rel_paths: list[str]) -> tuple[str, str] | None:
    """Read the first existing path under ``ROOT`` (for ``-n`` tags: match ``make test`` / local pins)."""
    for rel in rel_paths:
        rel = rel.replace("\\", "/")
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            return rel, path.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _git_show_first_existing(rev: str, rel_paths: list[str]) -> tuple[str, str] | None:
    for rel in rel_paths:
        text = _git_show_text(rev, rel)
        if text is not None:
            return rel, text
    return None


def _git_commit_exists(rev: str) -> bool:
    p = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{rev}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return p.returncode == 0


def _git_fetch_commit_from(url: str, rev: str) -> bool:
    p = subprocess.run(
        ["git", "-C", str(ROOT), "fetch", "--quiet", "--no-tags", url, rev],
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode == 0


def _ensure_n_tag_commit_from_canonical_upstream(variant: str, rev: str) -> bool:
    """Ensure ``rev`` is available for ``git show`` using the ODH or RHDS canonical ``.git`` URL for ``-n`` tags."""
    url = _CANONICAL_REPO_URL[variant]
    if _git_commit_exists(rev):
        return True
    return _git_fetch_commit_from(url, rev)


def _git_show_text(rev: str, rel_path: str) -> str | None:
    rel_path = rel_path.replace("\\", "/")
    p = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{rev}:{rel_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return None
    return p.stdout


def _format_dep_version(pep440: str) -> str:
    v = packaging.version.Version(pep440)
    return f"{v.major}.{v.minor}"


def _load_pylock_packages(pylock_text: str, python_minor: str) -> dict[str, dict[str, Any]]:
    doc = tomllib.loads(pylock_text)
    marker_env = {
        "python_full_version": f"{python_minor}.0",
        "python_version": python_minor,
        "implementation_name": "cpython",
        "sys_platform": "linux",
    }
    packages: dict[str, dict[str, Any]] = {}
    for p in doc.get("packages", []):
        if "marker" in p and not packaging.markers.Marker(p["marker"]).evaluate(marker_env):
            continue
        name = p["name"]
        if name in packages:
            raise ValueError(f"duplicate package in lockfile: {name}")
        packages[name] = p
    return packages


def _parse_requirements_txt_packages(text: str, python_minor: str) -> dict[str, dict[str, Any]]:
    """Parse pip-tools / pip ``requirements.txt`` (pinned ``pkg==ver`` lines; skips hash/index options)."""
    marker_env = {
        "python_full_version": f"{python_minor}.0",
        "python_version": python_minor,
        "implementation_name": "cpython",
        "sys_platform": "linux",
    }
    packages: dict[str, dict[str, Any]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--"):
            continue
        if line.startswith("-"):
            continue
        if "\\" in line:
            line = line.split("\\", 1)[0].strip()
        if "@" in line and "==" not in line:
            continue
        if "==" not in line:
            continue
        try:
            req = Requirement(line)
        except (InvalidRequirement, ValueError) as e:
            logger.debug("skip unparseable requirement line %r: %s", line, e)
            continue
        if req.marker is not None and not req.marker.evaluate(marker_env):
            continue
        pinned: str | None = None
        for spec in req.specifier:
            if spec.operator == "==":
                pinned = spec.version
                break
        if pinned is None:
            continue
        key = canonicalize_name(req.name)
        packages[key] = {"name": key, "version": pinned}
    return packages


def load_packages_from_lockfile(text: str, source_rel_path: str, python_minor: str) -> dict[str, dict[str, Any]]:
    name = Path(source_rel_path).name
    if name == "requirements.txt" or (name.startswith("requirements.") and name.endswith(".txt")):
        return _parse_requirements_txt_packages(text, python_minor)
    return _load_pylock_packages(text, python_minor)


def _python_minor_from_dir(notebook_dir: Path) -> str:
    _u, _l, py = notebook_dir.name.split("-")
    return py.removeprefix("python-")


# JSON inside YAML literal blocks: match upstream ImageStream style (``|`` not ``|2``); see
# ``jupyter-datascience-notebook-imagestream.yaml`` in opendatahub-io / mtchoum1 forks.
_JSON_OBJECT_SEP = (", ", ": ")


def _format_notebook_annotation_json(items: list[dict[str, Any]]) -> LiteralScalarString:
    """Format ``notebook-software`` / ``notebook-python-dependencies`` as a multiline literal block."""
    lines = ["["]
    pad = "  "
    for i, item in enumerate(items):
        blob = json.dumps(
            {"name": item["name"], "version": item["version"]},
            separators=_JSON_OBJECT_SEP,
            ensure_ascii=False,
        )
        suffix = "," if i < len(items) - 1 else ""
        lines.append(f"{pad}{blob}{suffix}")
    lines.append("]")
    text = "\n".join(lines) + "\n"
    return LiteralScalarString(text)


def _update_tag_annotations(
    tag: dict[str, Any],
    pylock_pkgs: dict[str, dict[str, Any]],
    python_display: str,
) -> None:
    ann = tag.get("annotations") or {}
    sw_raw = ann.get("opendatahub.io/notebook-software")
    dep_raw = ann.get("opendatahub.io/notebook-python-dependencies")
    if not sw_raw or not dep_raw:
        return
    sw = json.loads(str(sw_raw).strip())
    deps = json.loads(str(dep_raw).strip())
    for d in deps:
        name = d.get("name")
        if not name:
            continue
        norm = manifest_name_to_pip(name)
        pkg = pylock_pkgs.get(norm)
        if pkg is None:
            pkg = pylock_pkgs.get(canonicalize_name(norm))
        if pkg is None or "version" not in pkg:
            continue
        d["version"] = _format_dep_version(pkg["version"])

    # Keep ``notebook-software`` in sync with ``notebook-python-dependencies`` for the same display
    # name (``test_image_pyprojects`` requires matching strings). Only Python / accelerators are special-cased.
    sw_version_skip = frozenset({"CUDA", "ROCm", "R", "code-server"})
    dep_version_by_name = {d["name"]: d["version"] for d in deps if d.get("name")}
    for s in sw:
        n = s.get("name")
        if n == "Python":
            s["version"] = f"v{python_display}"
        elif n in sw_version_skip:
            continue
        elif n in dep_version_by_name:
            s["version"] = dep_version_by_name[n]

    ann["opendatahub.io/notebook-software"] = _format_notebook_annotation_json(sw)
    ann["opendatahub.io/notebook-python-dependencies"] = _format_notebook_annotation_json(deps)


def _sha_for_tag(
    base_key: str,
    suffix: str,
    latest: dict[str, str],
    released: dict[str, str],
) -> str | None:
    ck = f"{base_key}-commit{suffix}"
    sha = latest.get(ck) if suffix == "-n" else released.get(ck)
    if sha is None:
        return None
    normalized = sha.strip().lower()
    if not _GIT_HEX_OBJECT_ID.fullmatch(normalized):
        print(
            f"invalid commit SHA for {ck!r} (expected 7-40 hex chars): {sha!r}",
            file=sys.stderr,
        )
        return None
    return normalized


def run_variant(variant: str, dry_run: bool) -> int:
    manifests_dir = _manifests_variant_dir(variant)
    base = manifests_dir / "base"
    latest = parse_env_file(base / "commit-latest.env")
    released = parse_env_file(base / "commit.env")
    _all, workbenches, _rt_files, _runtimes = discover_config(base)

    yml = YAML()
    yml.preserve_quotes = True
    # Default width is 80; long scalars (e.g. notebook-image-desc, DockerImage names) get reflowed
    # onto the next line. Match manifests on main: single-line values where possible.
    yml.width = 1024 * 1024
    # Emit a YAML document start marker like other manifests in this repo (see main branch).
    yml.explicit_start = True
    yml.indent(mapping=2, sequence=4, offset=2)

    changed = 0
    lockfile_errors: list[str] = []
    candidate_dirs = _discover_candidate_dirs()
    for wb in workbenches:
        candidates = _dirs_for_workbench(manifests_dir, wb, candidate_dirs)
        path = base / wb.resource_file
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as f:
            docs = list(yml.load_all(f))
        if not docs:
            continue
        doc = docs[0]
        tags = doc.get("spec", {}).get("tags") or []
        for idx, (base_key, suffix) in enumerate(wb.versions):
            if idx >= len(tags):
                break
            sha = _sha_for_tag(base_key, suffix, latest, released)
            nb_dir = resolve_notebook_directory(candidates, base_key)
            if nb_dir is None:
                want = notebook_dirname_from_base_key(base_key)
                hint = f" (expected …/{want}/ in git or on disk)" if want else ""
                print(
                    f"skip {path.name} tag {idx}: no notebook dir for {base_key}{hint}",
                    file=sys.stderr,
                )
                continue
            kind = _pylock_kind_from_tag(wb.resource_file, base_key)
            rel_paths = pylock_candidate_rel_paths(nb_dir, kind)

            shown: tuple[str, str] | None
            if suffix == "-n":
                shown = _worktree_read_first_existing(rel_paths)
            else:
                shown = None

            if shown is None:
                if not sha:
                    print(f"skip {path.name} tag {idx}: no SHA for {base_key}{suffix}", file=sys.stderr)
                    continue
                if suffix == "-n" and not _ensure_n_tag_commit_from_canonical_upstream(variant, sha):
                    print(
                        f"skip {path.name} tag {idx}: could not resolve commit {sha} via "
                        f"{_CANONICAL_REPO_URL[variant]}",
                        file=sys.stderr,
                    )
                    continue
                shown = _git_show_first_existing(sha, rel_paths)
            if shown is None:
                print(
                    f"skip {path.name} tag {idx}: no lockfile (tried worktree/git {'; '.join(rel_paths)})",
                    file=sys.stderr,
                )
                continue
            rel_used, text = shown
            py_minor = _python_minor_from_dir(nb_dir)
            try:
                pkgs = load_packages_from_lockfile(text, rel_used, py_minor)
            except Exception as e:
                lockfile_errors.append(f"{path.name} tag {idx}: lockfile parse error: {e}")
                continue
            _update_tag_annotations(tags[idx], pkgs, py_minor)
            changed += 1

        if not dry_run:
            with path.open("w", encoding="utf-8") as f:
                if len(docs) > 1:
                    yml.dump_all(docs, f)
                else:
                    yml.dump(docs[0], f)
    if lockfile_errors:
        for err in lockfile_errors:
            print(err, file=sys.stderr)
        print(
            f"Aborting: {len(lockfile_errors)} lockfile parse error(s) for variant={variant!r}",
            file=sys.stderr,
        )
        return 1
    print(f"Updated {changed} tag annotation block(s) for variant={variant!r} (dry_run={dry_run})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("odh", "rhoai"), required=True)
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only; do not write YAML")
    args = parser.parse_args()
    raise SystemExit(run_variant(args.variant, args.dry_run))


if __name__ == "__main__":
    main()
