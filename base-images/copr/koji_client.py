# SPDX-License-Identifier: Apache-2.0
"""Koji API client for querying Fedora build metadata."""

from __future__ import annotations

import logging

import koji

from .models import PackageMetadata

logger = logging.getLogger(__name__)

# Koji dependency type constants
DEP_BUILDREQUIRES = 0  # BuildRequires on SRPMs use type 0 in Koji
DEP_PROVIDES = 1
DEP_REQUIRES = 2


class KojiClient:
    """Wrapper around the Koji XML-RPC API for querying package metadata."""

    def __init__(self, hub_url: str = "https://koji.fedoraproject.org/kojihub") -> None:
        self.session = koji.ClientSession(hub_url)

    def get_package_metadata(self, nvr: str) -> PackageMetadata:
        """Query Koji for a build's subpackages, provides, and BuildRequires.

        Args:
            nvr: Name-Version-Release string (e.g. 'hdf5-1.14.6-7.fc44')

        Returns:
            PackageMetadata with provides/build_requires populated from Koji.
        """
        build = self.session.getBuild(nvr, strict=True)
        rpms = self.session.listRPMs(buildID=build["id"])

        # Find SRPM
        srpm = next((r for r in rpms if r["arch"] == "src"), None)
        if srpm is None:
            msg = f"No SRPM found for build {nvr}"
            raise ValueError(msg)

        # Collect Provides from all binary RPMs
        provides: set[str] = set()
        for rpm in rpms:
            if rpm["arch"] == "src":
                continue
            deps = self.session.getRPMDeps(rpm["id"], depType=DEP_PROVIDES)
            provides.update(d["name"] for d in deps)

        # Get BuildRequires from SRPM
        # Note: Koji stores SRPM BuildRequires with type=0, not the usual
        # REQUIRES type (2).  We fetch all deps and filter by type.
        all_srpm_deps = self.session.getRPMDeps(srpm["id"])
        build_requires = {
            d["name"]
            for d in all_srpm_deps
            if d["type"] == DEP_BUILDREQUIRES and not d["name"].startswith("rpmlib(")
        }

        # Build SRPM download URL
        pathinfo = koji.PathInfo(topdir="https://kojipkgs.fedoraproject.org")
        srpm_url = pathinfo.build(build) + "/" + pathinfo.rpm(srpm)

        logger.info("Fetched metadata for %s: %d provides, %d build_requires", nvr, len(provides), len(build_requires))

        return PackageMetadata(
            name=build["name"],
            nvr=nvr,
            srpm_id=srpm["id"],
            srpm_url=srpm_url,
            provides=frozenset(provides),
            build_requires=frozenset(build_requires),
        )
