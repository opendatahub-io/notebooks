# SPDX-License-Identifier: Apache-2.0
"""Dependency resolution and topological sort for Copr rebuild ordering."""

from __future__ import annotations

import logging
from collections import defaultdict

from .models import BuildWave, PackageMetadata

logger = logging.getLogger(__name__)


def compute_build_waves(packages: dict[str, PackageMetadata]) -> list[BuildWave]:
    """Compute build waves via topological sort (Kahn's algorithm).

    Given a set of packages with their provides and build_requires,
    determine which packages can be built in parallel (same wave) and
    which must wait for earlier waves to complete.

    Algorithm:
        1. Build a global provides map: capability -> source package name
        2. For each package, intersect its BuildRequires with the provides map
           to find in-project dependency edges
        3. Topological sort (Kahn's algorithm) into waves

    Args:
        packages: Mapping of source package name to its metadata.

    Returns:
        Ordered list of BuildWave objects. Packages within a wave have
        no inter-dependencies and can be built in parallel.

    Raises:
        ValueError: If a dependency cycle is detected among the packages.
    """
    if not packages:
        return []

    # Step 1: provides map (only for packages in our set)
    provides_map: dict[str, str] = {}
    for pkg in packages.values():
        for cap in pkg.provides:
            provides_map[cap] = pkg.name

    # Step 2: build adjacency list
    # in_degree[pkg] = number of in-project packages it depends on
    in_degree: dict[str, int] = dict.fromkeys(packages, 0)
    dependents: dict[str, list[str]] = defaultdict(list)

    for pkg in packages.values():
        deps_in_project: set[str] = set()
        for req in pkg.build_requires:
            provider = provides_map.get(req)
            if provider is not None and provider != pkg.name:
                deps_in_project.add(provider)
        in_degree[pkg.name] = len(deps_in_project)
        for dep in deps_in_project:
            dependents[dep].append(pkg.name)

    logger.debug("Dependency edges: %s", dict(dependents))

    # Step 3: Kahn's algorithm, collecting by wave
    waves: list[BuildWave] = []
    queue = sorted(name for name, deg in in_degree.items() if deg == 0)
    wave_idx = 0

    while queue:
        waves.append(BuildWave(index=wave_idx, packages=list(queue)))
        next_queue: list[str] = []
        for pkg_name in queue:
            for dependent in dependents.get(pkg_name, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_queue.append(dependent)
        queue = sorted(next_queue)
        wave_idx += 1

    # Check for cycles
    scheduled_count = sum(len(w.packages) for w in waves)
    if scheduled_count != len(packages):
        remaining = sorted(n for n, d in in_degree.items() if d > 0)
        msg = f"Dependency cycle detected among: {remaining}"
        raise ValueError(msg)

    return waves
