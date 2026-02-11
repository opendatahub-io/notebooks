#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild Fedora packages for EL9 on Copr with automatic dependency ordering."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from base_images.copr.copr_client import CoprBuildError, CoprClient, CoprCliError
from base_images.copr.dependency_resolver import compute_build_waves
from base_images.copr.koji_client import KojiClient
from base_images.copr.models import Manifest

logger = logging.getLogger(__name__)


def load_manifest(path: Path) -> Manifest:
    """Load and validate a packages.yaml manifest file.

    Args:
        path: Path to the YAML manifest file.

    Returns:
        Validated Manifest model.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Manifest.model_validate(raw)


def configure_chroots(manifest: Manifest, copr: CoprClient) -> None:
    """Configure Copr chroots with extra packages and rpmbuild options.

    Args:
        manifest: The validated manifest.
        copr: Client for Copr operations.
    """
    if not manifest.chroots:
        return
    packages = manifest.chroot_packages or None
    rpmbuild_without = manifest.rpmbuild_without or None
    if not packages and not rpmbuild_without:
        return
    for chroot in manifest.chroots:
        copr.configure_chroot(chroot, packages=packages, rpmbuild_without=rpmbuild_without)


def run_dry_run(manifest: Manifest, koji_client: KojiClient) -> None:
    """Compute and display the build plan without submitting builds.

    Args:
        manifest: The validated manifest.
        koji_client: Client for querying Koji metadata.
    """
    packages = {}
    for entry in manifest.packages:
        logger.info("Querying Koji for %s ...", entry.nvr)
        meta = koji_client.get_package_metadata(entry.nvr)
        packages[meta.name] = meta

    waves = compute_build_waves(packages)

    print("Build plan:")
    print(f"  Copr project: {manifest.copr_project}")
    if manifest.chroots:
        print(f"  Chroots: {', '.join(manifest.chroots)}")
        if manifest.chroot_packages:
            print(f"  Extra buildroot packages: {', '.join(manifest.chroot_packages)}")
        if manifest.rpmbuild_without:
            print(f"  rpmbuild --without: {', '.join(manifest.rpmbuild_without)}")
    print(f"  Total packages: {len(packages)}")
    print(f"  Total waves: {len(waves)}")
    print()
    for wave in waves:
        print(f"  Wave {wave.index}:")
        for pkg_name in wave.packages:
            meta = packages[pkg_name]
            print(f"    - {meta.nvr}")
            print(f"      SRPM: {meta.srpm_url}")


def run_rebuild(manifest: Manifest, koji_client: KojiClient) -> None:
    """Execute the full rebuild: resolve dependencies, submit builds, wait for completion.

    Args:
        manifest: The validated manifest.
        koji_client: Client for querying Koji metadata.
    """
    packages = {}
    for entry in manifest.packages:
        logger.info("Querying Koji for %s ...", entry.nvr)
        meta = koji_client.get_package_metadata(entry.nvr)
        packages[meta.name] = meta

    waves = compute_build_waves(packages)

    copr = CoprClient(project=manifest.copr_project)
    configure_chroots(manifest, copr)
    for wave in waves:
        pkg_names = wave.packages
        print(f"=== Wave {wave.index}: {pkg_names} ===")
        urls = [packages[name].srpm_url for name in pkg_names]
        build_ids = copr.submit_wave(urls)
        print(f"  Submitted build IDs: {build_ids}")
        copr.wait_for_wave(build_ids)
        print(f"  Wave {wave.index} complete.")

    print("All waves complete.")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parent / "packages.yaml",
        help="Path to the packages.yaml manifest file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and display the build plan without submitting builds",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        manifest = load_manifest(args.manifest)
    except Exception as exc:
        print(f"Error: failed to load manifest {args.manifest}: {exc}", file=sys.stderr)
        sys.exit(1)

    koji_client = KojiClient()

    try:
        if args.dry_run:
            run_dry_run(manifest, koji_client)
        else:
            run_rebuild(manifest, koji_client)
    except CoprCliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if exc.stderr.strip():
            print(f"  stderr: {exc.stderr.strip()}", file=sys.stderr)
        if exc.stdout.strip():
            print(f"  stdout: {exc.stdout.strip()}", file=sys.stderr)
        print(f"  command: {' '.join(exc.command)}", file=sys.stderr)
        sys.exit(1)
    except CoprBuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
