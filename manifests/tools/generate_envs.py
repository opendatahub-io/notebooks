#!/usr/bin/env -S ./uv run --script

from __future__ import annotations

"""
Queries the Red Hat Ecosystem Catalog (catalog.redhat.com) for container image metadata
using the Pyxis REST API to generate params.env and commit.env files.

See docs/fetching_registry_redhat_io_index.md for API documentation and details.
"""

import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from typing import Any

import certifi
import typer

API_BASE = "https://catalog.redhat.com/api/containers/v1"
REGISTRY = "registry.access.redhat.com"


def get_json(url: str) -> dict[str, Any]:
    # Use certifi's CA bundle so TLS verification works on macOS, where Python's
    # bundled OpenSSL does not read from the system Keychain by default.
    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, context=ctx, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def main(
    version_tag: str = typer.Option(
        "v3.3", "--version-tag", "-v", help="The version tag to filter by (e.g., v3.3)"
    ),
    suffix: str = typer.Option(
        "2025-2", "--suffix", "-s", help="The suffix to append to variables (e.g., 2025-2)"
    ),
) -> None:
    if not re.match(
        r"""
        ^v          # leading 'v'
        \d+         # major
        \.          # dot
        \d+         # minor
        (           # optional patch
            \.
            \d+
        )?
        $
        """,
        version_tag,
        re.VERBOSE,
    ):
        print(f"Error: version_tag '{version_tag}' must match v<major>.<minor>[.<patch>] (e.g. v3.3)", file=sys.stderr)
        raise typer.Exit(code=1)

    try:
        repos: list[str] = []
        page = 0
        page_size = 100
        while True:
            url = (
                f"{API_BASE}/repositories?filter=repository=regex=rhoai/odh-workbench.*"
                f"&page_size={page_size}&page={page}&include=data.repository"
            )
            batch = get_json(url).get("data", [])
            repos.extend(item["repository"] for item in batch)
            if len(batch) < page_size:
                break
            page += 1
    except Exception as e:
        print(f"Error fetching repos: {e}", file=sys.stderr)
        sys.exit(1)

    params_env_lines = []
    commit_env_lines = []
    failures: list[str] = []

    for repo in sorted(repos):
        # NOTE: We filter by architecture==amd64 here merely to isolate a single
        # result entry for the API call. The `manifest_list_digest` field returned
        # represents the multi-arch manifest and is identical across all architectures.
        filter_str = f"architecture==amd64;repositories.tags.name=={version_tag}"
        encoded_filter = urllib.parse.quote(filter_str)

        img_url = f"{API_BASE}/repositories/registry/{REGISTRY}/repository/{repo}/images?page_size=1&page=0&filter={encoded_filter}&include=data.repositories.manifest_list_digest,data.parsed_data.labels"

        try:
            img_resp = get_json(img_url)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{repo}: {e}")
            continue

        data = img_resp.get("data", [])
        if not data:
            failures.append(f"{repo}: no image found for tag {version_tag}")
            continue

        img_data = data[0]

        manifest_list_digest = None
        for r in img_data.get("repositories", []):
            if "manifest_list_digest" in r:
                manifest_list_digest = r["manifest_list_digest"]
                break

        vcs_ref = None
        labels = img_data.get("parsed_data", {}).get("labels", [])
        for label in labels:
            if label.get("name") == "vcs-ref":
                vcs_ref = label.get("value")
                break

        if not manifest_list_digest or not vcs_ref:
            failures.append(f"{repo}: missing manifest_list_digest or vcs-ref")
            continue

        repo_name = repo.split("/")[-1]
        var_base_name = repo_name.replace("rhel9", "ubi9")

        param_line = f"{var_base_name}-{suffix}=registry.redhat.io/{repo}@{manifest_list_digest}"
        commit_line = f"{var_base_name}-commit-{suffix}={vcs_ref[:7]}"

        params_env_lines.append(param_line)
        commit_env_lines.append(commit_line)

    if failures:
        for failure in failures:
            print(f"Error: {failure}", file=sys.stderr)
        raise typer.Exit(code=1)

    print("=== params.env ===")
    for line in params_env_lines:
        print(line)

    print("\n=== commit.env ===")
    for line in commit_env_lines:
        print(line)


if __name__ == "__main__":
    typer.run(main)
