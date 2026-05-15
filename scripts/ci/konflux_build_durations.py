#!/usr/bin/env python3
"""Collect Konflux PipelineRun durations from Tekton Results API.

Queries the Tekton Results API on a Konflux cluster to extract
PipelineRun and TaskRun timing data. Used to compare Konflux build
times against GitHub Actions.

Prerequisites:
    - `oc` CLI logged in to the target cluster
    - Access to the tenant namespace

Usage:
    # ODH builds on stone-prd-rh01
    python scripts/ci/konflux_build_durations.py \\
        --host tekton-results-tekton-results.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com \\
        --namespace open-data-hub-tenant \\
        --context stone-prd-rh01

    # RHOAI builds on stone-prod-p02
    python scripts/ci/konflux_build_durations.py \\
        --host tekton-results-tekton-results.apps.stone-prod-p02.hjvn.p1.openshiftapps.com \\
        --namespace rhoai-tenant \\
        --context stone-prod-p02

Output: CSV with columns for pipeline duration, build phase, scan phase,
scheduling overhead, and per-task timing.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import subprocess
import sys
from datetime import datetime


def get_token(context_grep: str) -> str:
    ctx_result = subprocess.run(
        ["oc", "config", "get-contexts", "-o", "name"],
        capture_output=True, text=True, check=True,
    )
    contexts = ctx_result.stdout.strip().split("\n")
    matching = [c for c in contexts if context_grep in c]
    if not matching:
        print(f"No oc context matching '{context_grep}'. Available: {contexts}", file=sys.stderr)
        sys.exit(1)
    ctx = matching[0]
    token_result = subprocess.run(
        ["oc", "whoami", "-t", f"--context={ctx}"],
        capture_output=True, text=True, check=True,
    )
    return token_result.stdout.strip()


def tekton_results_query(host: str, token: str, namespace: str, filter_str: str = "", page_size: int = 50) -> list[dict]:
    """Query Tekton Results API and return decoded records."""
    import ssl
    import urllib.request
    import urllib.parse

    params = {"page_size": str(page_size)}
    if filter_str:
        params["filter"] = filter_str

    url = f"https://{host}/apis/results.tekton.dev/v1alpha2/parents/{namespace}/results/-/records?{urllib.parse.urlencode(params)}"

    # ROSA clusters use certs not in the default macOS trust store
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except (ImportError, Exception):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)
        return []

    records = []
    for record in data.get("records", []):
        record_data = record.get("data", {})
        value = record_data.get("value", "")
        if value:
            try:
                decoded = json.loads(base64.b64decode(value))
                records.append(decoded)
            except (json.JSONDecodeError, Exception):
                pass
    return records


def iso_to_datetime(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def duration_minutes(start: str | None, end: str | None) -> float | None:
    dt_start = iso_to_datetime(start)
    dt_end = iso_to_datetime(end)
    if not dt_start or not dt_end:
        return None
    return (dt_end - dt_start).total_seconds() / 60.0


BUILD_TASKS = {"init", "clone-repository", "prefetch-dependencies", "build-images", "build-image-index", "rhoai-init"}
SCAN_TASKS = {
    "clair-scan", "sast-snyk-check", "clamav-scan", "sast-coverity-check",
    "sast-shell-check", "sast-unicode-check", "rpms-signature-scan",
    "ecosystem-cert-preflight-checks", "deprecated-base-image-check",
    "build-source-image", "apply-tags", "push-dockerfile", "show-sbom",
    "send-slack-notification",
}


def classify_task(task_name: str) -> str:
    base = task_name.rsplit("-", 1)[0] if task_name and task_name[-1].isdigit() else task_name
    for prefix in BUILD_TASKS:
        if base.startswith(prefix):
            return "build"
    return "scan"


def extract_component_name(pr_name: str) -> str:
    """Extract component name from PipelineRun name like 'odh-workbench-jupyter-minimal-cpu-py312-ubi9-on-pushXXX'."""
    import re
    match = re.match(r"^(.*?)(?:-on-(?:push|pull-req))", pr_name)
    return match.group(1) if match else pr_name


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True, help="Tekton Results API hostname")
    parser.add_argument("--namespace", required=True, help="Konflux tenant namespace")
    parser.add_argument("--context", required=True, help="Substring to match oc context name")
    parser.add_argument("--limit", type=int, default=50, help="Max PipelineRuns to fetch")
    parser.add_argument("--output", default="-", help="Output CSV file (- for stdout)")
    args = parser.parse_args()

    print("Getting token...", file=sys.stderr)
    token = get_token(args.context)

    print(f"Querying PipelineRuns from {args.host}/{args.namespace}...", file=sys.stderr)
    records = tekton_results_query(
        args.host, token, args.namespace,
        filter_str='data_type == "tekton.dev/v1.PipelineRun"',
        page_size=args.limit,
    )

    if not records:
        print("No PipelineRun records found. Check host/namespace/token.", file=sys.stderr)
        print("Try: curl -s -w '%{http_code}' -o /dev/null "
              f"'https://{args.host}/apis/results.tekton.dev/v1alpha2/parents/{args.namespace}/results' "
              f"-H 'Authorization: Bearer <token>'", file=sys.stderr)
        return 1

    print(f"Found {len(records)} PipelineRun records", file=sys.stderr)

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="")
    writer = csv.writer(out)
    writer.writerow([
        "pipelinerun", "component", "date", "conclusion",
        "total_min", "build_phase_min", "scan_phase_min",
        "scheduling_overhead_min", "task_count",
    ])

    for pr in records:
        metadata = pr.get("metadata", {})
        status = pr.get("status", {})
        pr_name = metadata.get("name", "unknown")
        component = extract_component_name(pr_name)

        start_time = status.get("startTime")
        completion_time = status.get("completionTime")
        total_dur = duration_minutes(start_time, completion_time)

        conditions = status.get("conditions", [])
        conclusion = conditions[0].get("reason", "Unknown") if conditions else "Unknown"

        child_statuses = status.get("childReferences", [])
        task_runs = status.get("taskRuns", {})

        build_dur = 0.0
        scan_dur = 0.0
        task_execution_sum = 0.0
        task_count = 0

        # Try childReferences (newer Tekton) or inline taskRuns (older)
        for child in child_statuses:
            task_name = child.get("pipelineTaskName", "")
            tr_status = child.get("status", {})
            if not tr_status:
                continue
            tr_start = tr_status.get("startTime")
            tr_end = tr_status.get("completionTime")
            tr_dur = duration_minutes(tr_start, tr_end)
            if tr_dur is None:
                continue

            task_count += 1
            task_execution_sum += tr_dur
            phase = classify_task(task_name)
            if phase == "build":
                build_dur += tr_dur
            else:
                scan_dur += tr_dur

        scheduling_overhead = (total_dur - task_execution_sum) if total_dur and task_execution_sum else None

        date = (start_time or "")[:10]
        writer.writerow([
            pr_name,
            component,
            date,
            conclusion,
            f"{total_dur:.1f}" if total_dur else "",
            f"{build_dur:.1f}" if build_dur else "",
            f"{scan_dur:.1f}" if scan_dur else "",
            f"{scheduling_overhead:.1f}" if scheduling_overhead is not None else "",
            task_count,
        ])

    if args.output != "-":
        out.close()
        print(f"Wrote {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
