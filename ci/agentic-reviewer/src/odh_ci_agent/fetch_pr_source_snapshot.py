#!/usr/bin/env python3
"""Fetch a PR head snapshot into a local read-only analysis directory."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def tarball_request(repository: str, head_sha: str, token: str | None) -> Request:
    request = Request(
        f"https://api.github.com/repos/{repository}/tarball/{head_sha}",
        headers={"Accept": "application/vnd.github+json"},
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def strip_archive_root(name: str) -> PurePosixPath | None:
    parts = PurePosixPath(name).parts
    if len(parts) <= 1:
        return None
    stripped = PurePosixPath(*parts[1:])
    if not stripped.parts:
        return None
    if stripped.is_absolute() or ".." in stripped.parts:
        raise ValueError(f"Unsafe archive path: {name}")
    return stripped


def extract_snapshot_archive(archive_path: Path, destination: Path) -> tuple[int, int]:
    extracted_files = 0
    skipped_entries = 0
    with tarfile.open(archive_path, mode="r:*") as tar_handle:
        for member in tar_handle.getmembers():
            relative_path = strip_archive_root(member.name)
            if relative_path is None:
                continue

            target_path = destination / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            if not member.isfile():
                skipped_entries += 1
                continue

            extracted = tar_handle.extractfile(member)
            if extracted is None:
                skipped_entries += 1
                continue
            with extracted, open(target_path, "wb") as file_handle:
                shutil.copyfileobj(extracted, file_handle)
            extracted_files += 1

    return extracted_files, skipped_entries


def resolve_destination_workspace() -> Path:
    workspace_root = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()
    raw_destination = os.environ.get("SOURCE_WORKSPACE", "unsafe-pr-source").strip()
    if not raw_destination or raw_destination in {".", "/"}:
        raise SystemExit(f"Invalid SOURCE_WORKSPACE: {raw_destination!r}")

    destination = (workspace_root / raw_destination).resolve()
    if destination == workspace_root:
        raise SystemExit("SOURCE_WORKSPACE must not be the workspace root")
    try:
        destination.relative_to(workspace_root)
    except ValueError as err:
        raise SystemExit(f"SOURCE_WORKSPACE must stay under GITHUB_WORKSPACE: {raw_destination!r}") from err
    return destination


def main() -> None:
    repository = required_env("GITHUB_REPOSITORY")
    head_sha = required_env("PR_HEAD_SHA")
    destination = resolve_destination_workspace()
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None

    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with (
            urlopen(tarball_request(repository, head_sha, token), timeout=180) as response,  # noqa: S310
            open(temp_path, "wb") as out_file,
        ):
            shutil.copyfileobj(response, out_file)

        extracted_files, skipped_entries = extract_snapshot_archive(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)

    print(
        {
            "destination": str(destination),
            "extracted_files": extracted_files,
            "head_sha": head_sha,
            "repository": repository,
            "skipped_entries": skipped_entries,
        }
    )


if __name__ == "__main__":
    main()
