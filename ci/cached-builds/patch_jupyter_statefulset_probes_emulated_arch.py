#!/usr/bin/env python3
"""Widen Jupyter StatefulSet probes for slow CI (emulated ppc64le on GitHub-hosted runners).

RHAIENG-2818: under QEMU user-mode emulation, Jupyter can take many minutes to listen on
8888. Default liveness probes restart the container before startup completes.

This script is intended for CI only. Production / native-hardware deployments keep the
committed probe values in kustomize/base.

Usage:
  uv run python ci/cached-builds/patch_jupyter_statefulset_probes_emulated_arch.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

# Generous but bounded: first liveness check after 8m; ~12m more slack before restart.
_LIVENESS = {
    "initialDelaySeconds": 480,
    "periodSeconds": 15,
    "timeoutSeconds": 5,
    "successThreshold": 1,
    "failureThreshold": 48,
}
_READINESS = {
    "initialDelaySeconds": 480,
    "periodSeconds": 15,
    "timeoutSeconds": 5,
    "successThreshold": 1,
    "failureThreshold": 60,
}


def patch_statefulset(path: Path, yaml: YAML) -> bool:
    with path.open() as f:
        doc = yaml.load(f)
    if not doc or doc.get("kind") != "StatefulSet":
        return False
    containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    if not containers:
        return False
    c0 = containers[0]
    changed = False
    for key, template in (("livenessProbe", _LIVENESS), ("readinessProbe", _READINESS)):
        if key not in c0:
            continue
        probe = c0[key]
        for k, v in template.items():
            if k in ("tcpSocket", "httpGet", "exec"):
                continue
            if probe.get(k) != v:
                probe[k] = v
                changed = True
    if changed:
        with path.open("w") as f:
            yaml.dump(doc, f)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print paths that would be patched")
    args = parser.parse_args()
    root: Path = args.root

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    paths = sorted(root.glob("jupyter/**/kustomize/base/statefulset.yaml"))
    if not paths:
        print("No jupyter statefulset.yaml files found", file=sys.stderr)
        return 1

    patched: list[Path] = []
    for p in paths:
        if args.dry_run:
            print(f"would patch: {p.relative_to(root)}")
            continue
        if patch_statefulset(p, yaml):
            patched.append(p)

    if args.dry_run:
        print(f"dry-run: {len(paths)} file(s)")
        return 0

    for p in patched:
        print(f"patched probes: {p.relative_to(root)}")
    if not patched:
        print("no files required probe updates (unexpected)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
