#!/usr/bin/env python3
"""Write masked RENOVATE_HOST_RULES to GITHUB_ENV for GitHub Actions.

Reads Docker config.json from $DOCKER_CONFIG/config.json (same layout the workflow
prepares for Renovate) and converts auths entries into Renovate hostRules JSON.

Renovate's docker datasource applies hostRules reliably; relying on DOCKER_CONFIG alone
inside the renovate container is brittle across renovatebot/github-action versions.

The GitHub Actions mode registers every credential and the complete JSON payload with
``add-mask`` before writing the payload to GITHUB_ENV. Use ``--json`` for local callers
that need the compact JSON on stdout instead.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
from pathlib import Path


def _auth_entry_to_credentials(entry: dict[str, str]) -> tuple[str, str] | None:
    if entry.get("auth"):
        try:
            raw = base64.b64decode(entry["auth"]).decode()
        except binascii.Error, UnicodeDecodeError:
            return None
        if ":" in raw:
            user, password = raw.split(":", 1)
            return (user, password)
        return ("", raw)
    user = entry.get("username")
    password = entry.get("password")
    if user is not None and password is not None:
        return (str(user), str(password))
    return None


def docker_config_to_host_rules(config_path: Path) -> list[dict[str, str]]:
    data = json.loads(config_path.read_text())
    auths = data.get("auths") or {}
    rules: list[dict[str, str]] = []
    for raw_host, entry in auths.items():
        if not isinstance(entry, dict):
            continue
        host = raw_host.removeprefix("https://").removeprefix("http://").rstrip("/")
        creds = _auth_entry_to_credentials(entry)
        if not creds:
            continue
        user, password = creds
        rules.append(
            {
                "hostType": "docker",
                "matchHost": host,
                "username": user,
                "password": password,
            }
        )
    return rules


def _escape_workflow_command(value: str) -> str:
    """Escape data using the GitHub Actions workflow-command encoding."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _write_github_env(rules: list[dict[str, str]], github_env: Path) -> None:
    payload = json.dumps(rules, separators=(",", ":"))
    masked_values = dict.fromkeys(
        value for rule in rules for key in ("username", "password") if (value := rule.get(key))
    )
    if masked_values:
        masked_values[payload] = None
    for value in masked_values:
        print(f"::add-mask::{_escape_workflow_command(value)}", flush=True)

    delim = "RENOHOST"
    # https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#multiline-strings
    with github_env.open("a", encoding="utf-8") as env_file:
        env_file.write(f"RENOVATE_HOST_RULES<<{delim}\n{payload}\n{delim}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument(
        "--json",
        action="store_true",
        help="Print compact JSON only (for RENOVATE_HOST_RULES in a shell env).",
    )
    output.add_argument(
        "--github-env",
        type=Path,
        metavar="PATH",
        help="Mask credentials, then append RENOVATE_HOST_RULES to this GITHUB_ENV file.",
    )
    args = parser.parse_args()

    docker_config = os.environ.get("DOCKER_CONFIG", "").strip()
    if not docker_config:
        print("DOCKER_CONFIG is not set", file=sys.stderr)
        sys.exit(1)
    path = Path(docker_config) / "config.json"
    if not path.is_file():
        print(f"Missing Docker config: {path}", file=sys.stderr)
        sys.exit(1)
    rules = docker_config_to_host_rules(path)
    if args.json:
        print(json.dumps(rules, separators=(",", ":")))
        return
    _write_github_env(rules, args.github_env)


if __name__ == "__main__":
    main()
