#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
import typing

import structlog

from ci.logging_config import configure_logging

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ODH_MANIFEST_DIR = PROJECT_ROOT / "manifests" / "odh" / "base"
RHOAI_MANIFEST_DIR = PROJECT_ROOT / "manifests" / "rhoai" / "base"

log = structlog.get_logger()

DUMMY_IMAGE = "dummy"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill commit-latest.env with short vcs-ref values from image labels for params-latest.env."
    )
    parser.add_argument(
        "--odh-dir",
        type=pathlib.Path,
        default=ODH_MANIFEST_DIR,
        help=(
            "ODH directory containing params-latest.env (used as URL source of truth when "
            f"RHOAI params use '{DUMMY_IMAGE}') (default: manifests/odh/base under repo root)"
        ),
    )
    parser.add_argument(
        "--rhoai-dir",
        type=pathlib.Path,
        default=RHOAI_MANIFEST_DIR,
        help="RHOAI manifest directory (default: manifests/rhoai/base under repo root).",
    )
    parser.add_argument(
        "--only",
        choices=("both", "odh", "rhoai"),
        default="both",
        help="Which commit-latest.env file(s) to write (default: both).",
    )
    return parser.parse_args()


def resolve_manifest_dir(raw: pathlib.Path) -> pathlib.Path:
    return raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()


def load_params_env(path: pathlib.Path) -> list[tuple[str, str]]:
    with open(path, "rt") as file:
        return [
            (parts[0].strip(), parts[1].strip())
            for line in file
            if line.strip() and not line.strip().startswith("#")
            for parts in [line.strip().split("=", 1)]
            if len(parts) == 2
        ]


def resolve_rhoai_urls(
    rhoai_pairs: list[tuple[str, str]],
    odh_by_var: dict[str, str],
) -> list[tuple[str, str]]:
    """Replace RHOAI dummy placeholders with the same variable's image URL from ODH params."""
    out: list[tuple[str, str]] = []
    for var, raw in rhoai_pairs:
        if raw.strip().lower() == DUMMY_IMAGE:
            if var not in odh_by_var:
                log.error("No ODH params-latest entry to resolve RHOAI dummy image", variable=var)
                sys.exit(1)
            url = odh_by_var[var]
            if url.strip().lower() == DUMMY_IMAGE:
                log.error("ODH params-latest still has dummy for variable", variable=var)
                sys.exit(1)
            out.append((var, url))
        else:
            out.append((var, raw))
    return out


def write_commit_latest(
    var_url_pairs: list[tuple[str, str]],
    vcs_by_url: dict[str, str | None],
    commit_latest_path: pathlib.Path,
) -> None:
    lines: list[tuple[str, str]] = []
    for var, url in var_url_pairs:
        vcs = vcs_by_url[url]
        if vcs is None:
            log.error("Missing vcs-ref for image URL", url=url, variable=var)
            sys.exit(1)
        lines.append((re.sub(r"-n$", "-commit-n", var), vcs[:7]))

    with open(commit_latest_path, "wt") as file:
        for key, short in sorted(lines):
            print(key, short, file=file, sep="=")


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
    full_image_url = f"docker://{image_url}"

    command = ["skopeo", "inspect", "--override-os=linux", "--override-arch=amd64", "--retry-times=5", "--config", full_image_url]

    log.info(f"Starting config inspection for: {image_url}")

    stdout, stderr, returncode = None, None, None
    try:
        async with semaphore:
            log.info(f"Semaphore acquired, starting skopeo inspect for: {image_url}")
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            returncode = process.returncode

        if returncode != 0:
            log.error(f"Skopeo command failed for {image_url} with exit code {returncode}.")
            if stderr:
                log.error(f"Stderr: {stderr.decode().strip()}")
            return image_url, None

        if not stdout:
            log.error(f"Skopeo command returned success but stdout was empty for {image_url}.")
            return image_url, None

        image_config = json.loads(stdout.decode())

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
        log.error(f"Failed to parse skopeo output as JSON for {image_url}.")
        if stdout:
            log.debug(f"Stdout from skopeo for {image_url}: {stdout.decode(errors='replace')}")
        return image_url, None
    except Exception:
        log.exception("Unexpected error while processing image", image_url=image_url)
        return image_url, None


async def inspect_urls(urls: typing.Iterable[str]) -> dict[str, str | None]:
    unique = list(dict.fromkeys(urls))
    semaphore = asyncio.Semaphore(22)
    tasks = [get_image_vcs_ref(url, semaphore) for url in unique]
    results = await asyncio.gather(*tasks)
    out = dict(results)
    if any(v is None for v in out.values()):
        log.error("Failed to get commit hash for one or more images; aborting.")
        sys.exit(1)
    return out


async def main() -> None:
    args = parse_args()
    odh_dir = resolve_manifest_dir(args.odh_dir)
    rhoai_dir = resolve_manifest_dir(args.rhoai_dir)

    odh_params = odh_dir / "params-latest.env"
    rhoai_params = rhoai_dir / "params-latest.env"

    odh_by_var = dict(load_params_env(odh_params))

    targets: list[tuple[pathlib.Path, list[tuple[str, str]]]] = []

    if args.only in ("both", "odh"):
        odh_pairs = load_params_env(odh_params)
        if any(v.strip().lower() == DUMMY_IMAGE for _, v in odh_pairs):
            log.error("ODH params-latest.env must not use dummy image placeholders.")
            raise SystemExit(1)
        targets.append((odh_dir / "commit-latest.env", odh_pairs))

    if args.only in ("both", "rhoai"):
        rhoai_pairs = load_params_env(rhoai_params)
        rhoai_resolved = resolve_rhoai_urls(rhoai_pairs, odh_by_var)
        targets.append((rhoai_dir / "commit-latest.env", rhoai_resolved))

    all_urls: list[str] = []
    for _, pairs in targets:
        all_urls.extend(url for _, url in pairs)

    vcs_by_url = await inspect_urls(all_urls)

    for commit_path, pairs in targets:
        write_commit_latest(pairs, vcs_by_url, commit_path)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
