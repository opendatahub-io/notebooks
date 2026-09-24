#!/usr/bin/env python3
"""Orchestrate /fix-cve workflows (RHAIENG-7190).

Usage:
    python scripts/cve/fix_cve.py RHOAIENG-91786 --dry-run
    python scripts/cve/fix_cve.py CVE-2026-78676 --branch rhoai-3.5 --dry-run
    python scripts/cve/fix_cve.py --count 1 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.cve.cve_groups import CVEGroup, discover_open_groups, group_from_issue, resolve_input
from scripts.cve.jira_client import JiraClient
from scripts.cve.plan_fix import build_fix_plan, format_plan

ISSUE_FIELDS = "key,summary,status,labels,description,issuetype,issuelinks,project,components,due"


def _load_issue_from_fixture(fixture_dir: Path, issue_key: str) -> dict[str, Any]:
    fixture_path = (fixture_dir / f"{issue_key}.json").resolve()
    if fixture_path.parent != fixture_dir.resolve() or not fixture_path.is_file():
        raise SystemExit(f"fixture not found for {issue_key}: {fixture_path}")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _resolve_groups(
    client: JiraClient | None,
    args: argparse.Namespace,
) -> list:
    if args.issue_key and args.fixture_dir:
        issue = _load_issue_from_fixture(args.fixture_dir, args.issue_key)
        if client is None:
            cve_id = issue["fields"]["labels"][0]
            branch = "rhoai-3.5"
            for label in issue["fields"]["labels"]:
                if label.startswith("CVE-"):
                    cve_id = label
            match = re.search(r"\[(rhoai-\d+\.\d+)]", issue["fields"]["summary"])
            if match:
                branch = match.group(1)
            return [
                CVEGroup(
                    cve_id=cve_id,
                    branch=branch,
                    rhoaieng_keys=[args.issue_key],
                    summaries={args.issue_key: issue["fields"]["summary"]},
                )
            ]
        return [group_from_issue(client, issue)]

    if not client:
        raise SystemExit("Jira client required (set JIRA credentials or use --fixture-dir offline)")

    if args.issue_key:
        return resolve_input(client, args.issue_key, branch=args.branch)

    groups = discover_open_groups(client, max_results=args.max_results)
    if not groups:
        return []
    return groups[: args.count]


def _anchor_issue(client: JiraClient | None, group, args: argparse.Namespace) -> dict[str, Any]:
    anchor_key = group.anchor_key or args.issue_key
    if args.fixture_dir and anchor_key:
        try:
            return _load_issue_from_fixture(args.fixture_dir, anchor_key)
        except SystemExit:
            pass
    if client and anchor_key:
        return client.get_issue(anchor_key, ISSUE_FIELDS)
    raise SystemExit(f"unable to load anchor issue for group {group.group_key}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue_key", nargs="?", help="CVE id, RHAIENG key, or RHOAIENG key")
    parser.add_argument("--branch", help="Restrict CVE input to a single release branch")
    parser.add_argument("--count", type=int, default=1, help="Number of groups when discovering queue")
    parser.add_argument("--max-results", type=int, default=500, help="Max Jira issues to scan")
    parser.add_argument("--repo", default="red-hat-data-services/notebooks")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/unit/scripts/cve/fixtures/classify"),
        help="Offline Jira fixtures keyed by issue id",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no git/PR/Jira writes")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON plan output")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable plan JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    client: JiraClient | None
    try:
        client = JiraClient.from_env()
    except Exception:
        client = None

    groups = _resolve_groups(client, args)
    if not groups:
        print("No actionable CVE groups found.")
        return 1

    exit_code = 0
    for group in groups:
        anchor_issue = _anchor_issue(client, group, args)
        plan = build_fix_plan(
            group,
            anchor_issue=anchor_issue,
            repo=args.repo,
            repo_root=args.repo_root,
            dry_run=args.dry_run,
        )

        if args.json:
            indent = 2 if args.pretty else None
            print(json.dumps(plan.to_dict(), indent=indent))
        else:
            print(format_plan(plan))

        if plan.verdict in {"not_fixable", "needs_info"}:
            exit_code = 2

        if args.dry_run and not args.json:
            print("\nDry-run only — no git commits, PRs, or Jira updates performed.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
