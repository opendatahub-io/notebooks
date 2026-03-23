#!/usr/bin/env python3
"""Check that all image references in params env files exist in their container registries.

This is a focused availability check — it only verifies that images can be fetched,
not their labels, sizes, or other metadata (that's check-params-env-odh.sh's job).

Usage:
    python ci/check-image-availability.py manifests/odh/base/params-latest.env manifests/odh/base/params.env
"""

from __future__ import annotations

import asyncio
import pathlib
import shutil
import sys

import structlog

from ci.logging_config import configure_logging

log = structlog.get_logger()


async def check_image(image_url: str, semaphore: asyncio.Semaphore) -> tuple[str, bool]:
    """Check whether a container image exists in the registry.

    Uses `skopeo inspect --raw` which only fetches the manifest — the cheapest
    possible check for image existence.

    Returns:
        A tuple of (image_url, exists).
    """
    full_image_url = f"docker://{image_url}"
    command = [
        "skopeo",
        "inspect",
        "--override-os=linux",
        "--override-arch=amd64",
        "--retry-times=3",
        "--raw",
        full_image_url,
    ]

    try:
        async with semaphore:
            log.info("Checking image availability", image_url=image_url)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except TimeoutError:
                process.kill()
                await process.wait()
                log.error("Timeout checking image", image_url=image_url)
                return image_url, False

        if process.returncode != 0:
            stderr_text = stderr.decode().strip() if stderr else ""
            log.error("Image not found", image_url=image_url, stderr=stderr_text)
            return image_url, False

        log.info("Image exists", image_url=image_url)
        return image_url, True

    except Exception:
        log.exception("Unexpected error checking image", image_url=image_url)
        return image_url, False


def parse_env_file(path: pathlib.Path) -> list[tuple[str, str]]:
    """Parse a params env file into (variable, image_url) pairs.

    Skips empty lines, comments, and dummy values.
    """
    entries: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            variable, _, image_url = line.partition("=")
            if not image_url or image_url == "dummy":
                continue
            entries.append((variable, image_url))
    return entries


async def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <env-file> [<env-file> ...]", file=sys.stderr)
        return 2

    if shutil.which("skopeo") is None:
        log.error("The 'skopeo' command was not found. Please ensure it is installed and in your PATH.")
        return 2

    all_entries: list[tuple[str, str]] = []
    for arg in sys.argv[1:]:
        path = pathlib.Path(arg)
        if not path.exists():
            log.error("File not found", path=str(path))
            return 2
        entries = parse_env_file(path)
        log.info("Parsed env file", path=str(path), count=len(entries))
        all_entries.extend(entries)

    # Detect duplicate image URLs — two variables pointing to the same image is a bug
    seen_urls: dict[str, str] = {}
    for var, image_url in all_entries:
        if image_url in seen_urls:
            log.error(
                "Duplicate image URL detected",
                image_url=image_url,
                variable_1=seen_urls[image_url],
                variable_2=var,
            )
            return 1
        seen_urls[image_url] = var

    semaphore = asyncio.Semaphore(22)
    tasks = [check_image(image_url, semaphore) for _, image_url in all_entries]
    results = await asyncio.gather(*tasks)

    failed = [(seen_urls[url], url) for url, exists in results if not exists]

    log.info("Check complete", total=len(results), failed=len(failed))

    if failed:
        log.error("The following images were NOT found in their registries:")
        for var, url in failed:
            log.error("Missing image", variable=var, image_url=url)
        return 1

    log.info("All images are available in their registries.")
    return 0


if __name__ == "__main__":
    configure_logging()
    sys.exit(asyncio.run(main()))
