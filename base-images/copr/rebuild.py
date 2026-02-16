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
    """Configure Copr chroots with extra packages.

    Args:
        manifest: The validated manifest.
        copr: Client for Copr operations.
    """
    if not manifest.chroots or not manifest.chroot_packages:
        return
    for chroot in manifest.chroots:
        copr.configure_chroot(chroot, packages=manifest.chroot_packages)


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
    if manifest.build_timeout is not None:
        print(f"  Build timeout: {manifest.build_timeout}s ({manifest.build_timeout / 3600:.1f}h)")
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

    All waves are submitted upfront using Copr's batch ordering
    (``--with-build-id`` / ``--after-build-id``), so Copr enforces the
    correct build sequence server-side.  The tool then waits for all
    builds to complete.

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

    # Collect SRPM URLs grouped by wave
    wave_urls: list[list[str]] = []
    for wave in waves:
        urls = [packages[name].srpm_url for name in wave.packages]
        wave_urls.append(urls)

    # Submit all waves at once; Copr handles ordering via batches
    print(f"Submitting {len(packages)} packages in {len(waves)} waves ...")
    all_wave_ids = copr.submit_all_waves(wave_urls, timeout=manifest.build_timeout)

    # Report submitted build IDs
    for wave, wave_ids in zip(waves, all_wave_ids):
        print(f"  Wave {wave.index} ({wave.packages}): build IDs {wave_ids}")

    # Wait for all builds to complete
    all_build_ids = [bid for wave_ids in all_wave_ids for bid in wave_ids]
    print(f"Waiting for {len(all_build_ids)} builds to complete ...")
    copr.wait_for_wave(all_build_ids)

    print("All builds complete.")


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
