#!/usr/bin/env python3
"""
Update commit-latest.env files with vcs-ref labels from container images.

This script reads params-latest.env to get image digests, then uses skopeo
to inspect each image and extract the vcs-ref label (git commit hash).
The results are written to commit-latest.env.

Usage:
    python3 scripts/update-commit-latest-env.py --variant odh
    python3 scripts/update-commit-latest-env.py --variant rhoai
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
import typing

import structlog

try:
    from ci.logging_config import configure_logging
except ImportError:
    def configure_logging():
        import logging
        logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

log = structlog.get_logger()

# Mapping of variant to paths
VARIANT_PATHS = {
    "odh": {
        "params": PROJECT_ROOT / "manifests/odh/base/params-latest.env",
        "commit": PROJECT_ROOT / "manifests/odh/base/commit-latest.env",
    },
    "rhoai": {
        "params": PROJECT_ROOT / "manifests/rhoai/base/params-latest.env",
        "commit": PROJECT_ROOT / "manifests/rhoai/base/commit-latest.env",
    },
}


async def get_image_vcs_ref(image_url: str, semaphore: asyncio.Semaphore) -> tuple[str, str | None]:
    """
    Asynchronously inspects a container image's configuration using skopeo
    and extracts the 'vcs-ref' label.

    Args:
        image_url: The full URL of the image to inspect
                   (e.g., 'quay.io/opendatahub/workbench-images@sha256:...').

    Returns:
        A tuple containing the original image_url and the value of the 'vcs-ref'
        label if found, otherwise None.
    """
    # Using 'docker://' prefix is required for skopeo to identify the transport.
    full_image_url = f"docker://{image_url}"

    # Use 'inspect --config' which is much faster as it only fetches the config blob.
    command = ["skopeo", "inspect", "--override-os=linux", "--override-arch=amd64", "--retry-times=5", "--config", full_image_url]

    log.info(f"Starting config inspection for: {image_url}")

    stdout, stderr, returncode = None, None, None
    try:
        async with semaphore:
            log.info(f"Semaphore acquired, starting skopeo inspect for: {image_url}")
            # Create an asynchronous subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # Wait for the command to complete and capture output
            stdout, stderr = await process.communicate()
            returncode = process.returncode

        # Process the results outside the semaphore block
        if returncode != 0:
            log.error(f"Skopeo command failed for {image_url} with exit code {returncode}.")
            if stderr:
                log.error(f"Stderr: {stderr.decode().strip()}")
            return image_url, None

        if not stdout:
            log.error(f"Skopeo command returned success but stdout was empty for {image_url}.")
            return image_url, None

        # Decode and parse the JSON output from stdout
        # The output of 'inspect --config' is the image config JSON directly.
        image_config = json.loads(stdout.decode())

        # Safely extract the 'vcs-ref' label from the config's 'Labels'
        vcs_ref = image_config.get("config", {}).get("Labels", {}).get("vcs-ref")

        if vcs_ref:
            log.info(f"Successfully found 'vcs-ref' for {image_url}: {vcs_ref}")
        else:
            log.warning(f"'vcs-ref' label not found for {image_url}.")

        return image_url, vcs_ref

    except FileNotFoundError:
        log.error("The 'skopeo' command was not found. Please ensure it is installed and in your PATH.")
        return image_url, None
    except json.JSONDecodeError:
        # This error can now also happen if stdout is None or not valid JSON
        log.error(f"Failed to parse skopeo output as JSON for {image_url}.")
        if stdout:
            log.debug(f"Stdout from skopeo for {image_url}: {stdout.decode(errors='replace')}")
        return image_url, None
    except Exception as e:
        log.error("Unexpected error while processing image", image_url=image_url, exc_info=True)
        return image_url, None


async def inspect(images_to_inspect: typing.Iterable[str]) -> list[tuple[str, str | None]]:
    """
    Main function to orchestrate the concurrent inspection of multiple images.
    """
    semaphore = asyncio.Semaphore(22)  # Limit concurrent skopeo processes
    tasks = [get_image_vcs_ref(image, semaphore) for image in images_to_inspect]
    return await asyncio.gather(*tasks)


async def update_commit_env(variant: str) -> bool:
    """
    Update commit-latest.env for the specified variant (odh or rhoai).
    
    Returns True if successful, False otherwise.
    """
    paths = VARIANT_PATHS.get(variant)
    if not paths:
        log.error(f"Unknown variant: {variant}. Must be one of: {list(VARIANT_PATHS.keys())}")
        return False

    params_file = paths["params"]
    commit_file = paths["commit"]

    if not params_file.exists():
        log.warning(f"Params file not found: {params_file}. Skipping {variant}.")
        return True  # Not an error, just skip

    log.info(f"Processing {variant} variant")
    log.info(f"Reading params from: {params_file}")
    log.info(f"Will write commits to: {commit_file}")

    with open(params_file, "rt") as file:
        images_to_inspect: list[list[str]] = [
            line.strip().split('=', 1) for line in file.readlines()
            if line.strip() and not line.strip().startswith("#") and '=' in line
        ]

    if not images_to_inspect:
        log.warning(f"No images found in {params_file}")
        return True

    log.info(f"Found {len(images_to_inspect)} images to inspect")

    results = await inspect(value for _, value in images_to_inspect)
    
    # Check for failures but don't fail completely - just log warnings
    failed_count = sum(1 for _, commit_hash in results if commit_hash is None)
    if failed_count > 0:
        log.warning(f"Failed to get commit hash for {failed_count}/{len(results)} images")

    output = []
    for image, result in zip(images_to_inspect, results, strict=True):
        variable, image_digest = image
        _, commit_hash = result
        if commit_hash:
            # Convert variable name: remove trailing -n and add -commit-n
            commit_var = re.sub(r'-n$', "-commit-n", variable)
            output.append((commit_var, commit_hash[:7]))

    if output:
        # Ensure parent directory exists
        commit_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(commit_file, "wt") as file:
            for line in sorted(output):
                print(*line, file=file, sep="=", end="\n")
        
        log.info(f"Successfully wrote {len(output)} entries to {commit_file}")
    else:
        log.warning(f"No commit hashes to write for {variant}")

    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Update commit-latest.env with vcs-ref labels from container images"
    )
    parser.add_argument(
        "--variant",
        choices=["odh", "rhoai", "all"],
        default="all",
        help="Which variant to update (default: all)"
    )
    args = parser.parse_args()

    variants = list(VARIANT_PATHS.keys()) if args.variant == "all" else [args.variant]
    
    success = True
    for variant in variants:
        if not await update_commit_env(variant):
            success = False

    if not success:
        sys.exit(1)


if __name__ == '__main__':
    configure_logging()
    asyncio.run(main())
