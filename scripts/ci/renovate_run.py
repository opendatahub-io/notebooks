#!/usr/bin/env python3
"""Run Renovate in a container (Podman or Docker).

Same entrypoint as .github/workflows/renovate-self-hosted.yaml and local dev.

CONTAINER_ENGINE matches the Makefile (lines 65-74): if unset, use podman when
found on PATH, else docker. Override with CONTAINER_ENGINE=podman|docker.

  export GITHUB_MCP_PAT=ghp_...  # or RENOVATE_TOKEN (required for local/remote; optional for lookup)
  python3 scripts/ci/renovate_run.py            # platform=local, current tree
  python3 scripts/ci/renovate_run.py remote    # clone from GitHub
  python3 scripts/ci/renovate_run.py lookup    # local + --dry-run=lookup, JSON logs on stdout

Registry auth: DOCKER_CONFIG (default ~/.docker); sets RENOVATE_HOST_RULES from
config.json unless RENOVATE_HOST_RULES is already set (e.g. from GITHUB_ENV in CI).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS_CI = Path(__file__).resolve().parent
ROOT = SCRIPTS_CI.parent.parent
REMOTE_DEFAULT_REPO = "opendatahub-io/notebooks"
DEFAULT_RENOVATE_IMAGE = "quay.io/jdanek/renovate:43-fix42554"
DEFAULT_GIT_AUTHOR = "ide-developer <rhoai-ide-konflux@redhat.com>"

OPTIONAL_ENV_PASSTHROUGH = (
    "LOG_FORMAT",
    "RENOVATE_TOKEN",
    "RENOVATE_BASE_BRANCHES",
    "RENOVATE_ENABLED_MANAGERS",
    "RENOVATE_HOST_RULES",
    "RENOVATE_PLATFORM_COMMIT",
    "RENOVATE_REPOSITORIES",
    "GITHUB_COM_TOKEN",
    "NODE_OPTIONS",
    "NO_COLOR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


def detect_engine() -> str:
    raw = os.environ.get("CONTAINER_ENGINE", "").strip()
    if raw:
        if raw not in ("podman", "docker"):
            print(f"error: CONTAINER_ENGINE must be podman or docker (got {raw})", file=sys.stderr)
            sys.exit(1)
        return raw
    if shutil.which("podman"):
        return "podman"
    if shutil.which("docker"):
        return "docker"
    print("error: neither podman nor docker found on PATH", file=sys.stderr)
    sys.exit(1)


def maybe_load_host_rules(docker_config: str) -> None:
    if os.environ.get("RENOVATE_HOST_RULES"):
        return
    cfg = Path(docker_config) / "config.json"
    if not cfg.is_file():
        return
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_CI / "docker_config_to_renovate_host_rules.py"), "--json"],
        capture_output=True,
        text=True,
        env={**os.environ, "DOCKER_CONFIG": docker_config},
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        return
    rules = result.stdout.strip()
    if rules and rules != "[]":
        os.environ["RENOVATE_HOST_RULES"] = rules


def add_env_key(cmd: list[str], name: str) -> None:
    val = os.environ.get(name)
    if val is not None and val != "":
        cmd.extend(["-e", name])


def build_command(mode: str, engine: str, renovate_image: str, docker_config: str) -> list[str]:
    cmd: list[str] = [engine, "run", "--rm"]
    if sys.stdin.isatty() and sys.stdout.isatty():
        cmd.append("-t")
    cmd.append("-i")

    os.environ.setdefault("LOG_LEVEL", "info")
    os.environ.setdefault("RENOVATE_INHERIT_CONFIG", "false")
    os.environ.setdefault("RENOVATE_GIT_AUTHOR", DEFAULT_GIT_AUTHOR)

    cmd.extend(["-e", "LOG_LEVEL", "-e", "RENOVATE_INHERIT_CONFIG", "-e", "RENOVATE_GIT_AUTHOR"])

    if mode == "remote":
        os.environ.setdefault("RENOVATE_REPOSITORIES", REMOTE_DEFAULT_REPO)
    if mode == "lookup":
        os.environ.setdefault("LOG_FORMAT", "json")

    dry_run_keys: tuple[str, ...] = ()
    if mode in ("local", "remote"):
        dry_run_keys = ("RENOVATE_DRY_RUN",)

    for key in OPTIONAL_ENV_PASSTHROUGH + dry_run_keys:
        add_env_key(cmd, key)

    if Path(docker_config).is_dir():
        cmd.extend(["-e", "DOCKER_CONFIG", "-v", f"{docker_config}:{docker_config}:ro"])

    if mode in ("local", "lookup"):
        os.environ["RENOVATE_CONFIG_FILE"] = str(ROOT / ".github/renovate.json5")
        cmd.extend(
            [
                "-v",
                f"{ROOT}:{ROOT}",
                "-w",
                str(ROOT),
                "-e",
                "RENOVATE_CONFIG_FILE",
                renovate_image,
                "renovate",
                "--platform=local",
            ]
        )
        if mode == "lookup":
            cmd.append("--dry-run=lookup")
    elif mode == "remote":
        os.environ["RENOVATE_CONFIG_FILE"] = "/github-action/renovate.json5"
        cmd.extend(
            [
                "-v",
                f"{ROOT / '.github/renovate.json5'}:/github-action/renovate.json5:ro",
                "-e",
                "RENOVATE_CONFIG_FILE",
                renovate_image,
            ]
        )
    else:
        raise ValueError(mode)

    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="local",
        choices=("local", "remote", "lookup"),
        help="local: current tree; remote: clone repo; lookup: dry-run lookup + JSON logs",
    )
    args = parser.parse_args(argv)
    mode = args.mode

    engine = detect_engine()

    docker_config = os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker"))
    os.environ["DOCKER_CONFIG"] = docker_config

    if mode != "lookup" and not os.environ.get("RENOVATE_TOKEN"):
        print(f"error: set RENOVATE_TOKEN (required for {mode})", file=sys.stderr)
        return 1

    if not (Path(docker_config) / "config.json").is_file():
        print(
            f"warning: missing {docker_config}/config.json — private registry lookups may fail",
            file=sys.stderr,
        )

    maybe_load_host_rules(docker_config)

    renovate_image = os.environ.get("RENOVATE_IMAGE", DEFAULT_RENOVATE_IMAGE)

    cmd = build_command(mode, engine, renovate_image, docker_config)
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
