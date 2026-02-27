#!/usr/bin/env -S uv run --project=../..
"""Generate kustomization.yaml for manifests/base/.

Like the "99 bottles" or "12 days of Christmas" kata, the kustomization.yaml
is a highly repetitive file where each stanza follows the same template with
different parameters. This script expresses that pattern as code.

Works on both origin/main (2 versions per image) and rhds/main (up to 8
versions per image with py311/py312 split).  Image lists, version depths,
and ImageStream names are auto-discovered from the sibling .env and YAML
files -- no hardcoded image list to keep in sync.

Usage:
    uv run manifests/tools/generate_kustomization.py              # write kustomization.yaml
    uv run manifests/tools/generate_kustomization.py --check      # verify existing file matches
    uv run manifests/tools/generate_kustomization.py --stdout     # print to stdout instead
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ntb.strings import process_template_with_indents

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent / "base"
OUTPUT_FILE = BASE_DIR / "kustomization.yaml"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Workbench:
    """A workbench image with a variable-length version chain.

    Each entry in *versions* is a ``(base_key, suffix)`` tuple for that tag
    index.  The suffix is the full version suffix including the leading dash
    (e.g. ``"-n"``, ``"-2025-2"``, ``"-1-2"``).  This makes the script
    agnostic to the suffix style used on a given branch.

    For example, on rhds/main ``s2i-minimal-notebook`` has::

        versions = [
            ("odh-workbench-jupyter-minimal-cpu-py312-ubi9", "-n"),       # tag 0
            ("odh-workbench-jupyter-minimal-cpu-py312-ubi9", "-2025-2"),  # tag 1
            ("odh-workbench-jupyter-minimal-cpu-py311-ubi9", "-2025-1"),  # tag 2
            ...
        ]
    """

    imagestream: str
    resource_file: str
    versions: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Runtime:
    """A runtime image: single tag (N), params replacement only."""

    param_key: str
    imagestream: str
    resource_file: str


# ---------------------------------------------------------------------------
# Auto-discovery from .env and ImageStream YAML files
# ---------------------------------------------------------------------------

# Regex matching a params key like "odh-workbench-jupyter-minimal-cpu-py312-ubi9-2024-2"
#   group 1: everything before the version suffix (e.g. "odh-workbench-...-ubi9")
#   group 2: the "-n" or "-<version_major/year>-<version_minor>" suffix (e.g. "-2024-2")
_PARAM_KEY_RE = re.compile(
    r"""
    ^                   # Match the start of the string
    ( .+? )             # Group 1: Everything before the version suffix (non-greedy match)
    (                   # Group 2: The complete suffix
        -n              # Match the exact string "-n"
      |                 # OR
        -\d+-\d+        # Match a major/year and minor version (e.g., "-2024-2")
    )
    $                   # Match the end of the string
    """,
    re.VERBOSE
)



def _parse_env_keys(env_path: Path) -> set[str]:
    """Read an .env file and return the set of keys (left side of '=')."""
    keys: set[str] = set()
    if not env_path.exists():
        return keys
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, _ = line.partition("=")
        keys.add(key.strip())
    return keys


def _parse_imagestream_name(yaml_path: Path) -> str | None:
    """Extract ``metadata.name`` from an ImageStream YAML file.

    Uses a simple regex to avoid a PyYAML dependency at runtime.
    """
    text = yaml_path.read_text()
    # Match the top-level "  name: <value>" line that follows "metadata:"
    m = re.search(r"^metadata:\s*\n(?:\s+\S+:.*\n)*?\s+name:\s+(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


def discover_config(base_dir: Path) -> tuple[list[str], list[Workbench], list[str], list[Runtime]]:
    """Auto-discover workbenches, runtimes, resource files, and version chains.

    Returns (resource_files, workbenches, runtime_resource_files, runtimes)
    where *resource_files* is the workbench+extra resource list and
    *runtime_resource_files* is the runtime resource list (both in the order
    found in the existing kustomization.yaml).
    """
    # 1) Read the existing kustomization.yaml to get the resource ordering
    kustomization = (base_dir / "kustomization.yaml").read_text()
    resource_section = re.search(r"^resources:\n((?:\s+-\s+\S+\n)+)", kustomization, re.MULTILINE)
    assert resource_section, "Could not find resources section in kustomization.yaml"
    all_resources = [line.strip().lstrip("- ") for line in resource_section.group(1).splitlines() if line.strip()]

    # 1b) Build imagestream name -> resource file mapping from YAML metadata
    imagestream_to_resource = _build_imagestream_to_resource(base_dir, all_resources)

    # 2) Collect all param keys from .env files
    param_keys = _parse_env_keys(base_dir / "params.env") | _parse_env_keys(base_dir / "params-latest.env")

    # 3) Parse param keys into (base_key, suffix) pairs.
    #    e.g. "odh-workbench-...-ubi9-n"      -> ("odh-workbench-...-ubi9", "-n")
    #         "odh-workbench-...-ubi9-2025-2"  -> ("odh-workbench-...-ubi9", "-2025-2")
    #    We group by imagestream because different py versions share the same imagestream.

    # First, figure out which resource file each param key belongs to by matching
    # against the kustomization.yaml replacement blocks.  We do this by reading the
    # existing file structure.
    #
    # Simpler approach: parse the existing kustomization.yaml replacements section
    # to extract the ordered (key, imagestream) pairs.  This gives us exact ordering.

    replacements_text = kustomization[kustomization.index("replacements:"):]
    field_path_pattern = re.compile(r"fieldPath: data\.(\S+)")
    imagestream_pattern = re.compile(r"kind: ImageStream\n\s+name: (\S+)")

    # Extract pairs of (fieldPath_key, imagestream_name) from replacement blocks
    field_paths = field_path_pattern.findall(replacements_text)
    imagestreams = imagestream_pattern.findall(replacements_text)
    assert len(field_paths) == len(imagestreams), (
        f"Mismatch: {len(field_paths)} fieldPaths vs {len(imagestreams)} imagestreams"
    )

    # Split into params blocks and commit blocks
    params_pairs: list[tuple[str, str]] = []  # (full_key, imagestream)
    commit_pairs: list[tuple[str, str]] = []
    for key, istream in zip(field_paths, imagestreams, strict=True):
        if "-commit-" in key:
            commit_pairs.append((key, istream))
        else:
            params_pairs.append((key, istream))

    # Sanity check, ensure all params have corresponding imagestreams
    import unittest
    tc = unittest.TestCase()
    tc.maxDiff = None
    tc.assertCountEqual(param_keys, {full_key for full_key, _imagestream in params_pairs},
                        "Missing imagestream for param key")

    # 5) Build workbenches and runtimes from the params pairs
    workbench_resource_files: list[str] = []
    runtime_resource_files: list[str] = []
    workbenches: list[Workbench] = []
    runtimes: list[Runtime] = []

    # Track which imagestreams we've seen to group versions
    seen_workbench_imagestreams: dict[str, Workbench] = {}

    for full_key, istream in params_pairs:
        m = _PARAM_KEY_RE.match(full_key)
        assert m, f"Could not parse param key: {full_key}"
        base_key = m.group(1)
        suffix = m.group(2)

        if full_key.startswith("odh-pipeline-runtime-"):
            res_file = _find_resource_file(all_resources, istream, imagestream_to_resource)
            runtimes.append(Runtime(base_key, istream, res_file))
            if res_file not in runtime_resource_files:
                runtime_resource_files.append(res_file)
        else:
            if istream not in seen_workbench_imagestreams:
                res_file = _find_resource_file(all_resources, istream, imagestream_to_resource)
                wb = Workbench(istream, res_file)
                seen_workbench_imagestreams[istream] = wb
                workbenches.append(wb)
                if res_file not in workbench_resource_files:
                    workbench_resource_files.append(res_file)
            wb = seen_workbench_imagestreams[istream]
            wb.versions.append((base_key, suffix))

    # 6) Collect non-imagestream resources (buildconfigs, etc.) that are in
    #    the resource list but not matched to any workbench/runtime
    extra_resources: list[str] = []
    wb_and_rt_files = set(workbench_resource_files) | set(runtime_resource_files)
    for res in all_resources:
        if res not in wb_and_rt_files:
            extra_resources.append(res)

    # Build final resource list: workbench files + extra files + runtime files
    # Match the ordering in the existing kustomization.yaml
    ordered_resources = _order_resources(all_resources)

    return ordered_resources, workbenches, runtime_resource_files, runtimes


def _build_imagestream_to_resource(base_dir: Path, all_resources: list[str]) -> dict[str, str]:
    """Build a mapping from imagestream metadata.name to resource filename.

    Parses each YAML resource file to extract its ``metadata.name`` field,
    producing a reverse lookup so that imagestream names that don't match
    their filenames (e.g. ``s2i-minimal-notebook`` living inside
    ``jupyter-minimal-notebook-imagestream.yaml``) can still be resolved.
    """
    mapping: dict[str, str] = {}
    for res in all_resources:
        res_path = base_dir / res
        if not res_path.exists() or not res.endswith(".yaml"):
            continue
        istream_name = _parse_imagestream_name(res_path)
        if istream_name:
            if istream_name in mapping:
                raise ValueError(
                    f"Duplicate imagestream metadata.name {istream_name!r}: "
                    f"found in both {mapping[istream_name]!r} and {res!r}"
                )
            mapping[istream_name] = res
    return mapping


def _find_resource_file(
    all_resources: list[str],
    imagestream_name: str,
    imagestream_to_resource: dict[str, str],
) -> str:
    """Find the resource file for a given imagestream name.

    Tries exact match first, then the parsed metadata.name mapping,
    then falls back to substring matching.
    """
    # Common patterns: imagestream "runtime-minimal" -> "runtime-minimal-imagestream.yaml"
    exact = f"{imagestream_name}-imagestream.yaml"
    if exact in all_resources:
        return exact
    # Use the parsed metadata.name -> filename mapping
    if imagestream_name in imagestream_to_resource:
        return imagestream_to_resource[imagestream_name]
    # Fall back: find any resource containing the imagestream name
    for res in all_resources:
        if imagestream_name in res:
            return res
    raise ValueError(
        f"Could not find resource file for imagestream {imagestream_name!r} "
        f"in {all_resources}"
    )


def _order_resources(all_resources: list[str]) -> list[str]:
    """Deduplicate resources while preserving the existing kustomization.yaml order."""
    return list(dict.fromkeys(all_resources))


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------


def _replacement_block(
    field_path_key: str,
    configmap_name: str,
    target_field: str,
    imagestream_name: str,
) -> str:
    """One replacement stanza."""
    # language=yaml
    return process_template_with_indents(t"""\
  - source:
      fieldPath: data.{field_path_key}
      kind: ConfigMap
      name: {configmap_name}
      version: v1
    targets:
      - fieldPaths:
          - {target_field}
        select:
          group: image.openshift.io
          kind: ImageStream
          name: {imagestream_name}
          version: v1""")


def _workbench_params_replacements(wb: Workbench) -> list[str]:
    """Image-params replacements for all versions of a workbench."""
    blocks: list[str] = []
    for idx, (base_key, suffix) in enumerate(wb.versions):
        blocks.append(
            _replacement_block(
                f"{base_key}{suffix}",
                "notebook-image-params",
                f"spec.tags.{idx}.from.name",
                wb.imagestream,
            )
        )
    return blocks


def _workbench_commit_replacements(wb: Workbench) -> list[str]:
    """Commit-hash replacements for all versions of a workbench."""
    blocks: list[str] = []
    for idx, (base_key, suffix) in enumerate(wb.versions):
        blocks.append(
            _replacement_block(
                f"{base_key}-commit{suffix}",
                "notebook-image-commithash",
                f"spec.tags.{idx}.annotations.[opendatahub.io/notebook-build-commit]",
                wb.imagestream,
            )
        )
    return blocks


def _runtime_params_replacement(rt: Runtime) -> str:
    """Single image-params replacement for a runtime (N only)."""
    return _replacement_block(
        f"{rt.param_key}-n",
        "notebook-image-params",
        "spec.tags.0.from.name",
        rt.imagestream,
    )


def generate(base_dir: Path = BASE_DIR) -> str:
    """Produce the full kustomization.yaml content."""
    all_resources, workbenches, _runtime_resource_files, runtimes = discover_config(base_dir)

    resource_lines = "".join(f"  - {rf}\n" for rf in all_resources)
    resources = resource_lines.rstrip("\n")

    replacement_blocks: list[str] = []

    # 1) Workbench image-params for all workbenches (all versions)
    for wb in workbenches:
        replacement_blocks.extend(_workbench_params_replacements(wb))

    # 2) Workbench commit-hash for all workbenches (all versions)
    for wb in workbenches:
        replacement_blocks.extend(_workbench_commit_replacements(wb))

    # 3) Runtime image-params (N only) for all runtimes
    for rt in runtimes:
        replacement_blocks.append(_runtime_params_replacement(rt))

    # language=yaml
    return process_template_with_indents(t"""\
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
{resources}

configMapGenerator:
  - envs:
      - params.env
      - params-latest.env
    name: notebook-image-params
  - envs:
      - commit.env
      - commit-latest.env
    name: notebook-image-commithash
generatorOptions:
  disableNameSuffixHash: true

labels:
  - includeSelectors: true
    pairs:
      component.opendatahub.io/name: notebooks
      opendatahub.io/component: "true"
replacements:
{"\n".join(replacement_blocks)}
""")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Verify existing kustomization.yaml matches generated output")
    group.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing to file")
    args = parser.parse_args()

    content = generate()

    if args.check:
        existing = OUTPUT_FILE.read_text()
        if existing == content:
            print("OK: kustomization.yaml is up to date.")
        else:
            print("MISMATCH: kustomization.yaml differs from generated output.", file=sys.stderr)
            _print_first_difference(existing, content)
            sys.exit(1)
    elif args.stdout:
        sys.stdout.write(content)
    else:
        OUTPUT_FILE.write_text(content)
        print(f"Wrote {OUTPUT_FILE}")


def _print_first_difference(existing: str, generated: str) -> None:
    """Print a diagnostic showing the first line that differs."""
    existing_lines = existing.splitlines()
    generated_lines = generated.splitlines()
    for i, (e, g) in enumerate(zip(existing_lines, generated_lines, strict=False), 1):
        if e != g:
            print(f"  First difference at line {i}:", file=sys.stderr)
            print(f"    existing:  {e!r}", file=sys.stderr)
            print(f"    generated: {g!r}", file=sys.stderr)
            return
    shorter, longer = (
        ("existing", "generated")
        if len(existing_lines) < len(generated_lines)
        else ("generated", "existing")
    )
    print(f"  {shorter} has {abs(len(existing_lines) - len(generated_lines))} fewer lines than {longer}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
