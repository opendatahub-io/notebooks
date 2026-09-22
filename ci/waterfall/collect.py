#!/usr/bin/env python3
"""Collect workbench build data from Konflux (oc + KubeArchive). Prometheus disabled — exporter off."""

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_COMPONENT_RE = r"workbenches-operator|workbenches-controller"
SOURCE_RANK = {"live": 2, "archived": 1}

# Generous caps so slow clusters / KubeArchive don't fail spuriously; still bounded.
OC_TIMEOUT_SEC = 180       # live pipelinerun list
KA_TIMEOUT_SEC = 600       # archived pipelineruns per component query
OC_CONTEXT_TIMEOUT_SEC = 30  # oc config get-contexts
KA_WORKERS = 8             # parallel component queries (bounded)
HISTORY_MAX_PER_KEY = 50   # timeline cap per component×branch row
TR_CLASSIFY_WORKERS = 8    # parallel TaskRun lookups for failure detail
TR_TIMEOUT_SEC = 90        # per PipelineRun TaskRun list

# Pipeline tasks whose failure means the image build itself failed (not a post-build check).
BUILD_PIPELINE_TASKS = frozenset({
    "rhoai-init",
    "init",
    "clone-repository",
    "prefetch-dependencies",
    "build-images",
    "build-image-index",
    "build-source-image",
})

# Canonical Konflux component name stems (before -ubi9 or -{rhoai-version} suffix).
# Matches .tekton/*-ubi9-push.yaml and RHDS rhoai-*-push.yaml naming.
NOTEBOOK_COMPONENT_STEMS = [
    "odh-workbench-jupyter-minimal-cpu-py312",
    "odh-workbench-jupyter-minimal-cuda-py312",
    "odh-workbench-jupyter-minimal-rocm-py312",
    "odh-workbench-jupyter-datascience-cpu-py312",
    "odh-workbench-jupyter-pytorch-cuda-py312",
    "odh-workbench-jupyter-pytorch-rocm-py312",
    "odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312",
    "odh-workbench-jupyter-tensorflow-cuda-py312",
    "odh-workbench-jupyter-tensorflow-rocm-py312",
    "odh-workbench-jupyter-trustyai-cpu-py312",
    "odh-workbench-codeserver-datascience-cpu-py312",
    "odh-pipeline-runtime-minimal-cpu-py312",
    "odh-pipeline-runtime-datascience-cpu-py312",
    "odh-pipeline-runtime-pytorch-cuda-py312",
    "odh-pipeline-runtime-pytorch-rocm-py312",
    "odh-pipeline-runtime-pytorch-llmcompressor-cuda-py312",
    "odh-pipeline-runtime-tensorflow-cuda-py312",
    "odh-pipeline-runtime-tensorflow-rocm-py312",
]
# RHDS EA streams may use truncated workbench name for llmcompressor (63-char limit).
RHDS_LLM_WORKBENCH_STEM = "odh-wb-jupyter-pytorch-llmcompressor-cuda-py312"

# KubeArchive: only supported release streams (no auto-discovery of ancient rhoai-v2-*).
TRACKED_RHDS_APPLICATIONS = [
    "rhoai-v2-25",
    "rhoai-v3-3",
    "rhoai-v3-4",
    "rhoai-v3-5",
    "rhoai-v3-6-ea-1",
]

TRACKED_RHDS_BRANCHES = frozenset({
    "rhoai-2.25",
    "rhoai-3.3",
    "rhoai-3.4",
    "rhoai-3.5",
    "rhoai-3.6-ea.1",
})

# ODH midstream: opendatahub-io/notebooks main pushes + PRs targeting main.
ODH_TRACKED_BRANCHES = frozenset({"main"})

CLUSTERS = {
    "odh": {
        "context_grep": "stone-prd-rh01",
        "namespace": "open-data-hub-tenant",
        "instance": "stone-prd-rh01",
        "ui_base": "https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com",
        "applications": ["opendatahub-builds"],
        "tracked_branches": ODH_TRACKED_BRANCHES,
    },
    "rhds": {
        "context_grep": "stone-prod-p02",
        "namespace": "rhoai-tenant",
        "instance": "stone-prod-p02",
        "ui_base": "https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com",
        "applications": TRACKED_RHDS_APPLICATIONS,
        "tracked_branches": TRACKED_RHDS_BRANCHES,
    },
}


def get_oc_context(grep_pattern: str) -> str | None:
    result = subprocess.run(
        ["oc", "config", "get-contexts", "-o", "name"],
        capture_output=True,
        text=True,
        timeout=OC_CONTEXT_TIMEOUT_SEC,
    )
    for line in result.stdout.splitlines():
        if grep_pattern in line:
            return line.strip()
    return None


def component_matches_workbench(name: str) -> bool:
    if re.search(EXCLUDED_COMPONENT_RE, name):
        return False
    return bool(re.search(r"odh-workbench-|odh-wb-|odh-pipeline-runtime-", name))


def odh_component_names() -> list[str]:
    return [f"{stem}-ubi9" for stem in NOTEBOOK_COMPONENT_STEMS]


def rhds_component_names(application: str) -> list[str]:
    suffix = application.removeprefix("rhoai-")
    names = [f"{stem}-{suffix}" for stem in NOTEBOOK_COMPONENT_STEMS]
    names.append(f"{RHDS_LLM_WORKBENCH_STEM}-{suffix}")
    return names


def archived_component_names(cfg: dict) -> list[str]:
    names: list[str] = []
    for application in cfg["applications"]:
        if application == "opendatahub-builds":
            names.extend(odh_component_names())
        else:
            names.extend(rhds_component_names(application))
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(names))


def branch_tracked(entry: dict, tracked_branches: frozenset[str]) -> bool:
    return (entry.get("branch") or "") in tracked_branches


def merge_key(entry: dict) -> tuple[str, str]:
    """Separate main vs PR@main rows (matches UI version labels)."""
    branch = entry.get("branch") or entry.get("application") or ""
    if entry.get("event_type") == "pull_request":
        return entry["component"], f"PR@{branch}"
    return entry["component"], branch


def pipelinerun_to_entry(item: dict, cluster_name: str, cfg: dict, source: str) -> dict:
    labels = item["metadata"].get("labels", {})
    annotations = item["metadata"].get("annotations", {})
    conditions = item.get("status", {}).get("conditions", [])
    succeeded = next((c for c in conditions if c.get("type") == "Succeeded"), {})
    component = labels.get("appstudio.openshift.io/component", "")
    application = labels.get("appstudio.openshift.io/application", "")
    return {
        "name": item["metadata"]["name"],
        "component": component,
        "application": application,
        "sha": labels.get("pipelinesascode.tekton.dev/sha", ""),
        "branch": annotations.get("build.appstudio.redhat.com/target_branch", ""),
        "event_type": labels.get("pipelinesascode.tekton.dev/event-type", ""),
        "status": succeeded.get("status", "Unknown"),
        "reason": succeeded.get("reason", ""),
        "start": item.get("status", {}).get("startTime"),
        "completion": item.get("status", {}).get("completionTime"),
        "created": item["metadata"].get("creationTimestamp"),
        "cluster": cluster_name,
        "source": source,
        "ui_url": (
            f"{cfg['ui_base']}/ns/{cfg['namespace']}"
            f"/applications/{application}/components/{component}/activity/pipelineruns"
        ),
    }


def get_live_pipelineruns(
    context: str, namespace: str, cluster_name: str, cfg: dict,
) -> list:
    try:
        result = subprocess.run(
            [
                "oc", "get", "pipelinerun", "-n", namespace, "--context", context,
                "-l", "pipelines.appstudio.openshift.io/type=build",
                "-o", "json",
            ],
            capture_output=True,
            text=True,
            timeout=OC_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"  [warn] oc get pipelinerun timed out after {OC_TIMEOUT_SEC}s", file=sys.stderr)
        return []
    if result.returncode != 0:
        print(f"  [warn] oc get pipelinerun failed: {result.stderr[:200]}", file=sys.stderr)
        return []

    runs = []
    for item in json.loads(result.stdout).get("items", []):
        component = item["metadata"].get("labels", {}).get("appstudio.openshift.io/component", "")
        if not component_matches_workbench(component):
            continue
        entry = pipelinerun_to_entry(item, cluster_name, cfg, "live")
        if not branch_tracked(entry, cfg["tracked_branches"]):
            continue
        runs.append(entry)
    return runs


def get_archived_for_component(
    context: str, namespace: str, component: str, cluster_name: str, cfg: dict,
) -> list:
    """KubeArchive query scoped to one workbench/runtime component label."""
    label = (
        "pipelines.appstudio.openshift.io/type=build,"
        f"appstudio.openshift.io/component={component}"
    )
    try:
        result = subprocess.run(
            [
                "kubectl", "ka", "get", "pipelineruns", "-n", namespace,
                "--context", context, "--archived=true",
                "-l", label,
                "-o", "json",
            ],
            capture_output=True,
            text=True,
            timeout=KA_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"  [warn] ka get {component} timed out after {KA_TIMEOUT_SEC}s", file=sys.stderr)
        return []
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if stderr:
            print(f"  [warn] ka get {component}: {stderr[:160]}", file=sys.stderr)
        return []

    runs = []
    for item in json.loads(result.stdout or "{}").get("items", []):
        entry = pipelinerun_to_entry(item, cluster_name, cfg, "archived")
        if not branch_tracked(entry, cfg["tracked_branches"]):
            continue
        runs.append(entry)
    return runs


def collect_archived(
    context: str, namespace: str, cluster_name: str, cfg: dict, component_names: list[str],
) -> list:
    archived: list = []
    hits = 0
    with ThreadPoolExecutor(max_workers=KA_WORKERS) as pool:
        futures = {
            pool.submit(
                get_archived_for_component, context, namespace, component, cluster_name, cfg,
            ): component
            for component in component_names
        }
        for future in as_completed(futures):
            component = futures[future]
            try:
                runs = future.result()
            except Exception as exc:
                print(f"  [warn] ka get {component}: {exc}", file=sys.stderr)
                continue
            if runs:
                hits += 1
                archived.extend(runs)
    print(f"  KubeArchive: {hits}/{len(component_names)} component(s) with archived builds", file=sys.stderr)
    return archived


def merge_runs(entries: list) -> list:
    """Latest per (component, version row); live beats archived."""
    best: dict[tuple[str, str], dict] = {}
    for entry in entries:
        key = merge_key(entry)
        current = best.get(key)
        if current is None:
            best[key] = entry
            continue
        entry_rank = SOURCE_RANK.get(entry["source"], 0)
        current_rank = SOURCE_RANK.get(current["source"], 0)
        if entry_rank > current_rank:
            best[key] = entry
        elif entry_rank == current_rank and (entry.get("created") or "") > (current.get("created") or ""):
            best[key] = entry
    return list(best.values())


def build_history(live: list, archived: list) -> list:
    """All runs for timeline view: dedupe by PipelineRun name (live wins), capped per cell key."""
    by_name: dict[str, dict] = {}
    for entry in archived:
        by_name[entry["name"]] = entry
    for entry in live:
        by_name[entry["name"]] = entry

    buckets: dict[tuple[str, str], list] = {}
    for entry in by_name.values():
        buckets.setdefault(merge_key(entry), []).append(entry)

    history: list = []
    for runs in buckets.values():
        runs.sort(key=lambda item: item.get("created") or "", reverse=True)
        history.extend(runs[:HISTORY_MAX_PER_KEY])
    return history


def baseline_failure_class(entry: dict) -> str:
    if entry.get("reason") == "Running":
        return "running"
    if entry.get("status") == "True":
        return "ok"
    if entry.get("status") == "False":
        return "failed"
    return "unknown"


def failure_class_from_tasks(failed_tasks: list[str]) -> str:
    if not failed_tasks:
        return "failed"
    if any(task in BUILD_PIPELINE_TASKS for task in failed_tasks):
        return "build_failed"
    return "check_failed"


def taskrun_failed_pipeline_tasks(taskruns: list) -> list[str]:
    failed: list[str] = []
    for taskrun in taskruns:
        conditions = taskrun.get("status", {}).get("conditions", [])
        succeeded = next((c for c in conditions if c.get("type") == "Succeeded"), {})
        if succeeded.get("status") == "True":
            continue
        task = taskrun.get("metadata", {}).get("labels", {}).get("tekton.dev/pipelineTask", "")
        if task:
            failed.append(task)
    return sorted(set(failed))


def get_taskruns_for_pipelinerun(
    context: str, namespace: str, pipelinerun_name: str, archived: bool,
) -> list:
    label = f"tekton.dev/pipelineRun={pipelinerun_name}"
    if archived:
        cmd = [
            "kubectl", "ka", "get", "taskruns", "-n", namespace,
            "--context", context, "--archived=true",
            "-l", label, "-o", "json",
        ]
        timeout = KA_TIMEOUT_SEC
    else:
        cmd = [
            "oc", "get", "taskrun", "-n", namespace, "--context", context,
            "-l", label, "-o", "json",
        ]
        timeout = TR_TIMEOUT_SEC
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return []
    if result.returncode != 0:
        return []
    return json.loads(result.stdout or "{}").get("items", [])


def classify_pipelinerun_failure(
    context: str, namespace: str, entry: dict,
) -> tuple[str, list[str]]:
    taskruns = get_taskruns_for_pipelinerun(
        context, namespace, entry["name"], archived=entry.get("source") == "archived",
    )
    failed_tasks = taskrun_failed_pipeline_tasks(taskruns)
    return failure_class_from_tasks(failed_tasks), failed_tasks


def enrich_failure_classes(context: str, namespace: str, entries: list) -> dict[str, dict]:
    """Classify failed PipelineRuns via TaskRuns; returns name -> detail."""
    failed = [entry for entry in entries if entry.get("status") == "False"]
    if not failed:
        return {}

    details: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=TR_CLASSIFY_WORKERS) as pool:
        futures = {
            pool.submit(classify_pipelinerun_failure, context, namespace, entry): entry["name"]
            for entry in failed
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                failure_class, failed_tasks = future.result()
            except Exception as exc:
                print(f"  [warn] classify {name}: {exc}", file=sys.stderr)
                continue
            details[name] = {
                "failure_class": failure_class,
                "failed_tasks": failed_tasks,
            }
    return details


def apply_failure_classes(entries: list, details: dict[str, dict]) -> None:
    for entry in entries:
        entry["failure_class"] = baseline_failure_class(entry)
        detail = details.get(entry["name"])
        if detail:
            entry["failure_class"] = detail["failure_class"]
            if detail.get("failed_tasks"):
                entry["failed_tasks"] = detail["failed_tasks"]


def collect_cluster(cluster_name: str, cfg: dict) -> tuple[list, list]:
    ctx = get_oc_context(cfg["context_grep"])
    if not ctx:
        print(f"  [warn] No context for {cluster_name}", file=sys.stderr)
        return [], []

    print(f"Collecting {cluster_name} ({ctx})...", file=sys.stderr)

    live = get_live_pipelineruns(ctx, cfg["namespace"], cluster_name, cfg)
    print(f"  live PipelineRuns: {len(live)}", file=sys.stderr)

    applications = cfg["applications"]
    component_names = archived_component_names(cfg)
    print(
        f"  KubeArchive: {len(component_names)} component selector(s) "
        f"({len(applications)} application(s))",
        file=sys.stderr,
    )

    archived = collect_archived(ctx, cfg["namespace"], cluster_name, cfg, component_names)

    combined = live + archived
    merged = merge_runs(combined)

    # TaskRun lookups only for live + latest-per-cell failures (not full history).
    to_classify: dict[str, dict] = {entry["name"]: entry for entry in live}
    for entry in merged:
        if entry.get("status") == "False":
            to_classify[entry["name"]] = entry
    failure_details = enrich_failure_classes(ctx, cfg["namespace"], list(to_classify.values()))

    apply_failure_classes(live, failure_details)
    apply_failure_classes(archived, failure_details)
    apply_failure_classes(merged, failure_details)

    history = build_history(live, archived)
    apply_failure_classes(history, failure_details)

    classified = sum(1 for d in failure_details.values() if d.get("failed_tasks"))
    check_failed = sum(1 for d in failure_details.values() if d.get("failure_class") == "check_failed")
    build_failed = sum(1 for d in failure_details.values() if d.get("failure_class") == "build_failed")
    if failure_details:
        print(
            f"  failure detail: {classified}/{len(failure_details)} via TaskRuns "
            f"({build_failed} build, {check_failed} check)",
            file=sys.stderr,
        )

    print(f"  merged: {len(merged)} component×branch entries", file=sys.stderr)
    print(f"  history: {len(history)} timeline build(s)", file=sys.stderr)
    return merged, history


def main():
    pipelineruns = {}
    history = {}
    for cluster_name, cfg in CLUSTERS.items():
        merged, cluster_history = collect_cluster(cluster_name, cfg)
        pipelineruns[cluster_name] = merged
        history[cluster_name] = cluster_history

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "oc+kubearchive",
        "prometheus_metrics": [],
        "live_pipelineruns": pipelineruns,
        "pipelinerun_history": history,
    }

    out_path = Path(__file__).parent / "data.json"
    out_path.write_text(json.dumps(output, indent=2))
    total = sum(len(v) for v in pipelineruns.values())
    hist_total = sum(len(v) for v in history.values())
    print(
        f"\nWrote {out_path} ({out_path.stat().st_size} bytes, "
        f"{total} latest + {hist_total} history)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
