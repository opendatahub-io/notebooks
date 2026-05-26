#!/usr/bin/env python3
"""Remote Renovate dry-run checks for PR title prefix behavior."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_CI = Path(__file__).resolve().parent
ROOT = SCRIPTS_CI.parent.parent
RENOVATE_RUN = SCRIPTS_CI / "renovate_run.py"
DEFAULT_DRY_RUN_TIMEOUT_SECONDS = 900

KNOWN_CONFIG_WARNINGS = (
    "You must configure baseBranchPatterns in order to use them inside matchBaseBranches.",
    'The "allowedCommands" option is a global option',
    'The "autodiscover" option is a global option',
    'The "customEnvVariables" option is a global option',
    'The "inheritConfig" option is a global option',
    'The "onboarding" option is a global option',
    'The "requireConfig" option is a global option',
)

RunSubprocess = Callable[..., subprocess.CompletedProcess[str]]


def _subprocess_stream_text(data: str | bytes | None) -> str:
    if not data:
        return ""
    return data if isinstance(data, str) else data.decode()


@dataclass(frozen=True)
class DryRunScenario:
    name: str
    repository: str
    base_branch: str
    require_prefix: str | None


SCENARIOS = (
    DryRunScenario(
        name="odh-main",
        repository="opendatahub-io/notebooks",
        base_branch="main",
        require_prefix=None,
    ),
    DryRunScenario(
        name="rhds-rhoai-3.4",
        repository="red-hat-data-services/notebooks",
        base_branch="rhoai-3.4",
        require_prefix="[rhoai-3.4]",
    ),
)


def parse_json_log_lines(output: str) -> list[dict]:
    records: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def extract_pr_titles(records: list[dict]) -> list[str]:
    titles: list[str] = []
    for record in records:
        if isinstance(record.get("prTitle"), str):
            titles.append(record["prTitle"])
        branches = record.get("branchesInformation")
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict) and isinstance(branch.get("prTitle"), str):
                    titles.append(branch["prTitle"])
    return titles


def is_known_config_warning(message: str) -> bool:
    return any(known in message for known in KNOWN_CONFIG_WARNINGS)


def fatal_config_warnings(records: list[dict]) -> list[str]:
    warnings: list[str] = []
    for record in records:
        for warning in record.get("warnings", []):
            if not isinstance(warning, dict):
                continue
            message = warning.get("message")
            if not isinstance(message, str):
                continue
            if is_known_config_warning(message):
                continue
            warnings.append(message)
    return warnings


def validate_scenario_titles(scenario: DryRunScenario, titles: list[str]) -> list[str]:
    errors: list[str] = []
    if not titles:
        errors.append(f"{scenario.name}: no prTitle values found in Renovate dry-run output")
        return errors

    if scenario.require_prefix is None:
        prefixed = [title for title in titles if title.startswith("[")]
        if prefixed:
            errors.append(
                f"{scenario.name}: expected unprefixed PR titles on {scenario.base_branch}, "
                f"got prefixed examples: {prefixed[:3]}"
            )
        return errors

    matching = [title for title in titles if title.startswith(scenario.require_prefix)]
    if not matching:
        errors.append(
            f"{scenario.name}: expected at least one PR title starting with "
            f"{scenario.require_prefix!r}, got: {titles[:5]}"
        )
    return errors


def build_dry_run_env(scenario: DryRunScenario, base_env: Mapping[str, str]) -> dict[str, str]:
    env = dict(base_env)
    env.setdefault("LOG_FORMAT", "json")
    env.setdefault("LOG_LEVEL", "debug")
    env.setdefault("RENOVATE_DRY_RUN", "full")
    env.setdefault("RENOVATE_ENABLED_MANAGERS", "github-actions")
    env["RENOVATE_REPOSITORIES"] = scenario.repository
    env["RENOVATE_BASE_BRANCHES"] = scenario.base_branch
    return env


def run_dry_run(
    scenario: DryRunScenario,
    *,
    env: Mapping[str, str],
    timeout_seconds: int = DEFAULT_DRY_RUN_TIMEOUT_SECONDS,
    renovate_run: Path = RENOVATE_RUN,
    root: Path = ROOT,
    runner: RunSubprocess = subprocess.run,
) -> tuple[list[dict], str]:
    try:
        proc = runner(
            [sys.executable, str(renovate_run), "remote"],
            cwd=root,
            env=dict(env),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        combined = _subprocess_stream_text(exc.stdout) + _subprocess_stream_text(exc.stderr)
        tail = combined[-4000:] if combined else ""
        raise RuntimeError(f"{scenario.name}: renovate dry-run timed out after {timeout_seconds}s\n{tail}") from exc
    combined = proc.stdout + proc.stderr
    if proc.returncode != 0:
        msg = f"{scenario.name}: renovate dry-run exited {proc.returncode}"
        raise RuntimeError(f"{msg}\n{combined[-4000:]}")
    return parse_json_log_lines(combined), combined


def validate_dry_runs(
    *,
    scenarios: Sequence[DryRunScenario] = SCENARIOS,
    renovate_token: str | None = None,
    base_env: Mapping[str, str] | None = None,
    timeout_seconds: int = DEFAULT_DRY_RUN_TIMEOUT_SECONDS,
    runner: RunSubprocess = subprocess.run,
) -> list[str]:
    token = renovate_token if renovate_token is not None else os.environ.get("RENOVATE_TOKEN")
    if not token:
        return ["RENOVATE_TOKEN is not set"]

    env_base = dict(os.environ if base_env is None else base_env)
    env_base["RENOVATE_TOKEN"] = token

    errors: list[str] = []
    for scenario in scenarios:
        try:
            records, _ = run_dry_run(
                scenario,
                env=build_dry_run_env(scenario, env_base),
                timeout_seconds=timeout_seconds,
                runner=runner,
            )
        except RuntimeError as exc:
            errors.append(str(exc))
            continue

        errors.extend(f"{scenario.name}: unexpected config warning: {msg}" for msg in fatal_config_warnings(records))
        errors.extend(validate_scenario_titles(scenario, extract_pr_titles(records)))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    timeout_raw = os.environ.get("RENOVATE_DRY_RUN_TIMEOUT_SECONDS")
    timeout_seconds = int(timeout_raw) if timeout_raw else DEFAULT_DRY_RUN_TIMEOUT_SECONDS

    errors = validate_dry_runs(timeout_seconds=timeout_seconds)
    if errors:
        print("Renovate dry-run validation failed:", file=sys.stderr)
        for message in errors:
            print(f"  - {message}", file=sys.stderr)
        return 1

    print("OK: Renovate dry-run prefix checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
