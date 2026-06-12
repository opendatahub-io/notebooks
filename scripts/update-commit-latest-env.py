#!/usr/bin/env python3
"""Refresh ``manifests/odh/base/commit-latest.env`` from ``vcs-ref`` image labels.

Reads ``params-latest.env``, inspects each image with ``skopeo``, writes 7-char git prefixes.
Run after changing ``params-latest.env`` (e.g. pinning workbench images to digests from ``params.env``).
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sys
import typing

import structlog

from ci.logging_config import configure_logging

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

log = structlog.get_logger()


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


async def main():
    with open(PROJECT_ROOT / "manifests/odh/base/params-latest.env", "rt") as file:
        images_to_inspect: list[list[str]] = [line.strip().split('=', 1) for line in file.readlines()
                                              if line.strip() and not line.strip().startswith("#")]

    results = await inspect(value for _, value in images_to_inspect)
    if any(commit_hash is None for variable, commit_hash in results):
        log.error("Failed to get commit hash for some images. Quitting, please try again to try again, like.")
        sys.exit(1)

    output = []
    for image, result in zip(images_to_inspect, results, strict=True):
        variable, image_digest = image
        _, commit_hash = result
        output.append((re.sub(r'-n$', "-commit-n", variable), commit_hash[:7]))

    with open(PROJECT_ROOT / "manifests/odh/base/commit-latest.env", "wt") as file:
        for line in sorted(output):
            print(*line, file=file, sep="=", end="\n")


if __name__ == '__main__':
    configure_logging()
    asyncio.run(main())
