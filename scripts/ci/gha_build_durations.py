#!/usr/bin/env python3
"""Collect GitHub Actions build durations for ROI analysis.

Queries the last N push builds on main via `gh api` and outputs a CSV
with per-job timing data. Used to compare GHA build times against
Konflux pipeline durations.

Usage:
    python scripts/ci/gha_build_durations.py [--limit 10] [--workflow build-notebooks-push.yaml]

Output columns:
    run_id, date, image, platform, variant, duration_min, conclusion, workflow_min
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone


def gh_api(endpoint: str) -> dict:
    result = subprocess.run(
        ["gh", "api", endpoint, "--paginate"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def gh_run_list(repo: str, workflow: str, branch: str, limit: int) -> list[dict]:
    result = subprocess.run(
        [
            "gh", "run", "list",
            "--repo", repo,
            "--workflow", workflow,
            "--branch", branch,
            "--limit", str(limit),
            "--json", "databaseId,createdAt,updatedAt,conclusion,headSha",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def gh_run_jobs(repo: str, run_id: int) -> list[dict]:
    result = subprocess.run(
        [
            "gh", "run", "view", str(run_id),
            "--repo", repo,
            "--json", "jobs",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout).get("jobs", [])


def parse_job_name(name: str) -> tuple[str, str, str]:
    """Parse job name like 'jupyter-minimal-ubi9-python-3.12 · linux/amd64 / odh'.

    Returns (image, platform, variant).
    """
    match = re.match(r"^(.+?)\s*·\s*(linux/\w+)\s*/?\s*(\w+)?", name)
    if match:
        image = match.group(1).strip()
        platform = match.group(2).strip()
        variant = (match.group(3) or "").strip()
        return image, platform, variant
    return name, "", ""


def iso_to_datetime(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def duration_minutes(start: str, end: str) -> float:
    if not start or not end:
        return 0.0
    dt_start = iso_to_datetime(start)
    dt_end = iso_to_datetime(end)
    return (dt_end - dt_start).total_seconds() / 60.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="opendatahub-io/notebooks")
    parser.add_argument("--workflow", default="build-notebooks-push.yaml")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent workflow runs to analyze")
    parser.add_argument("--output", default="-", help="Output CSV file (- for stdout)")
    args = parser.parse_args()

    runs = gh_run_list(args.repo, args.workflow, args.branch, args.limit)
    runs = [r for r in runs if r.get("conclusion") in ("success", "failure")]

    if not runs:
        print("No completed runs found", file=sys.stderr)
        return 1

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="")
    writer = csv.writer(out)
    writer.writerow([
        "run_id", "date", "image", "platform", "variant",
        "duration_min", "conclusion", "workflow_duration_min",
    ])

    for run in runs:
        run_id = run["databaseId"]
        run_date = run["createdAt"][:10]
        workflow_dur = duration_minutes(run["createdAt"], run["updatedAt"])

        print(f"Processing run {run_id} ({run_date})...", file=sys.stderr)

        jobs = gh_run_jobs(args.repo, run_id)
        for job in jobs:
            if job.get("conclusion") == "skipped":
                continue
            name = job.get("name", "")
            if name in ("Generate job matrix",):
                continue

            image, platform, variant = parse_job_name(name)
            dur = duration_minutes(job.get("startedAt", ""), job.get("completedAt", ""))

            writer.writerow([
                run_id,
                run_date,
                image,
                platform,
                variant,
                f"{dur:.1f}",
                job.get("conclusion", ""),
                f"{workflow_dur:.1f}",
            ])

    if args.output != "-":
        out.close()
        print(f"Wrote {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
