#!/usr/bin/env python3
"""Chart successful Konflux build durations over time, per component.

Reads ``data.json`` produced by ``collect.py`` (live PipelineRuns + KubeArchive
history) and writes an interactive Plotly HTML chart (CDN; no extra deps).

By default embeds several stages (pipeline / build / push / sbom / prefetch)
so you can switch them in the page. Pass ``--stage`` once or repeatedly to
override which stages are included.

Examples::

    python3 chart_durations.py --cluster odh --event-type push
    python3 chart_durations.py --stage build --stage push
    python3 chart_durations.py --stage sbom --component codeserver
    python3 chart_durations.py --stage 'build-images:sbom-syft-generate'
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

SUCCESS_STATUS = "True"
TR_TIMEOUT_SEC = 120
TR_WORKERS = 8

# Presets map to pipeline task + optional step names within that task.
# Steps are summed within each TaskRun; multi-arch TaskRuns are aggregated
# via --matrix-agg (default max = wall-clock of the parallel matrix).
STAGE_PRESETS: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "pipeline": ("", None),  # whole PipelineRun; sentinel
    "build": ("build-images", ("build",)),
    "push": ("build-images", ("push",)),
    "sbom": (
        "build-images",
        ("sbom-syft-generate", "prepare-sboms", "upload-sbom"),
    ),
    "prefetch": ("prefetch-dependencies", None),
    "build-images": ("build-images", None),
    "clair": ("clair-scan", None),
    "clamav": ("clamav-scan", None),
}

# Default stages shown in the HTML stage dropdown when --stage is omitted.
DEFAULT_UI_STAGES = ("pipeline", "build", "push", "sbom", "prefetch")

CLUSTER_NS = {
    "odh": {
        "context_grep": "open-data-hub-tenant/api-stone-prd-rh01",
        "namespace": "open-data-hub-tenant",
    },
    "rhds": {
        "context_grep": "rhoai-tenant/api-stone-prod-p02",
        "namespace": "rhoai-tenant",
    },
}


@dataclass(frozen=True)
class StageSpec:
    """Empty task_name means whole PipelineRun duration."""

    key: str
    task_name: str
    step_names: tuple[str, ...] | None  # None = whole task

    @property
    def needs_taskruns(self) -> bool:
        return bool(self.task_name)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_stage(raw: str) -> StageSpec:
    key = raw.strip()
    if key in STAGE_PRESETS:
        task, steps = STAGE_PRESETS[key]
        return StageSpec(key=key, task_name=task, step_names=steps)
    if ":" in key:
        task, step = key.split(":", 1)
        task, step = task.strip(), step.strip()
        if not task or not step:
            raise ValueError(f"bad --stage {raw!r}; expected task:step")
        return StageSpec(key=key, task_name=task, step_names=(step,))
    return StageSpec(key=key, task_name=key, step_names=None)


def load_runs(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    by_name: dict[str, dict] = {}

    def consider(run: dict) -> None:
        name = run.get("name")
        if not name:
            return
        prev = by_name.get(name)
        if prev is None:
            by_name[name] = run
            return
        rank = (1 if run.get("completion") else 0, 1 if run.get("source") == "live" else 0)
        prev_rank = (
            1 if prev.get("completion") else 0,
            1 if prev.get("source") == "live" else 0,
        )
        if rank >= prev_rank:
            by_name[name] = run

    for runs in (data.get("live_pipelineruns") or {}).values():
        for run in runs:
            consider(run)
    for runs in (data.get("pipelinerun_history") or {}).values():
        for run in runs:
            consider(run)

    return list(by_name.values())


def filter_successful_runs(
    runs: list[dict],
    *,
    clusters: set[str] | None,
    event_types: set[str] | None,
    branches: set[str] | None,
    component_substrings: list[str],
    since: datetime | None,
) -> list[dict]:
    out: list[dict] = []
    for run in runs:
        if run.get("status") != SUCCESS_STATUS:
            continue
        start = parse_ts(run.get("start"))
        end = parse_ts(run.get("completion"))
        if start is None or end is None or end < start:
            continue
        if clusters and run.get("cluster") not in clusters:
            continue
        if event_types and (run.get("event_type") or "") not in event_types:
            continue
        if branches and (run.get("branch") or "") not in branches:
            continue
        component = run.get("component") or ""
        if component_substrings and not any(s in component for s in component_substrings):
            continue
        if since and end < since:
            continue
        out.append(
            {
                "name": run.get("name", ""),
                "component": component,
                "cluster": run.get("cluster", ""),
                "branch": run.get("branch", ""),
                "event_type": run.get("event_type", ""),
                "application": run.get("application", ""),
                "sha": (run.get("sha") or "")[:12],
                "start": start,
                "completion": end,
                "duration_min": (end - start).total_seconds() / 60.0,
                "ui_url": run.get("ui_url", ""),
                "source": run.get("source", ""),
                "platform": "",
            }
        )
    out.sort(key=lambda r: r["completion"])
    return out


def get_oc_context(grep_pattern: str) -> str | None:
    result = subprocess.run(
        ["oc", "config", "get-contexts", "-o", "name"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    for line in result.stdout.splitlines():
        if grep_pattern in line:
            return line.strip()
    return None


def fetch_taskruns(context: str, namespace: str, pipelinerun: str, archived: bool) -> list[dict]:
    label = f"tekton.dev/pipelineRun={pipelinerun}"
    if archived:
        cmd = [
            "kubectl",
            "ka",
            "get",
            "taskruns",
            "-n",
            namespace,
            "--context",
            context,
            "--archived=true",
            "-l",
            label,
            "-o",
            "json",
        ]
    else:
        cmd = [
            "oc",
            "get",
            "taskrun",
            "-n",
            namespace,
            "--context",
            context,
            "-l",
            label,
            "-o",
            "json",
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TR_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return []
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout or "{}").get("items", [])
    except json.JSONDecodeError:
        return []


def _step_duration_min(step: dict) -> float | None:
    term = step.get("terminated") or {}
    start = parse_ts(term.get("startedAt"))
    end = parse_ts(term.get("finishedAt"))
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 60.0


def _task_duration_min(taskrun: dict) -> float | None:
    status = taskrun.get("status") or {}
    start = parse_ts(status.get("startTime"))
    end = parse_ts(status.get("completionTime"))
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 60.0


def _platform_of(taskrun: dict) -> str:
    labels = taskrun.get("metadata", {}).get("labels") or {}
    for key in (
        "build.appstudio.redhat.com/target-platform",
        "build.appstudio.redhat.com/cloud-dynamic-platform",
    ):
        if labels.get(key):
            return labels[key]
    for param in taskrun.get("spec", {}).get("params") or []:
        if param.get("name") == "PLATFORM" and param.get("value"):
            return str(param["value"])
    return "unknown"


def index_taskruns(taskruns: list[dict]) -> list[dict]:
    """Flatten TaskRuns into cacheable timing records."""
    records: list[dict] = []
    for tr in taskruns:
        labels = tr.get("metadata", {}).get("labels") or {}
        task = labels.get("tekton.dev/pipelineTask") or ""
        if not task:
            continue
        steps: dict[str, float] = {}
        for step in (tr.get("status") or {}).get("steps") or []:
            name = step.get("name")
            dur = _step_duration_min(step)
            if name and dur is not None:
                steps[name] = dur
        task_dur = _task_duration_min(tr)
        records.append(
            {
                "task": task,
                "platform": _platform_of(tr),
                "duration_min": task_dur,
                "steps": steps,
            }
        )
    return records


def stage_platform_durs_from_index(
    records: list[dict],
    stage: StageSpec,
) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for rec in records:
        if rec["task"] != stage.task_name:
            continue
        if stage.step_names is None:
            dur = rec.get("duration_min")
        else:
            steps = rec.get("steps") or {}
            total = 0.0
            missing = False
            for name in stage.step_names:
                if name not in steps:
                    missing = True
                    break
                total += float(steps[name])
            dur = None if missing else total
        if dur is not None:
            out.append((rec.get("platform") or "unknown", float(dur)))
    return out


def aggregate_matrix(
    platform_durs: list[tuple[str, float]],
    how: str,
) -> list[tuple[str, float]]:
    if not platform_durs:
        return []
    if how == "each":
        return platform_durs
    vals = [d for _, d in platform_durs]
    if how == "sum":
        return [("", sum(vals))]
    return [("", max(vals))]


def load_stage_cache(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_stage_cache(path: Path, cache: dict) -> None:
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def ensure_taskrun_indexes(
    rows: list[dict],
    *,
    cache_path: Path,
    contexts: dict[str, str],
) -> dict:
    """Fetch TaskRuns once per PipelineRun; cache under key ``tridx|<name>``."""
    cache = load_stage_cache(cache_path)
    missing = [row for row in rows if f"tridx|{row['name']}" not in cache]
    if not missing:
        return cache

    print(
        f"fetching TaskRuns for {len(missing)} PipelineRuns (workers={TR_WORKERS})…",
        file=sys.stderr,
    )

    def fetch_one(row: dict) -> tuple[str, list[dict] | None]:
        cluster = row["cluster"]
        cfg = CLUSTER_NS.get(cluster)
        context = contexts.get(cluster)
        if not cfg or not context:
            return row["name"], None
        archived = row.get("source") != "live"
        taskruns = fetch_taskruns(context, cfg["namespace"], row["name"], archived)
        if not taskruns and archived:
            taskruns = fetch_taskruns(context, cfg["namespace"], row["name"], archived=False)
        if not taskruns:
            return row["name"], None
        return row["name"], index_taskruns(taskruns)

    with ThreadPoolExecutor(max_workers=TR_WORKERS) as pool:
        futures = {pool.submit(fetch_one, row): row["name"] for row in missing}
        done = 0
        for future in as_completed(futures):
            name, records = future.result()
            cache[f"tridx|{name}"] = {
                "records": records,
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            done += 1
            if done % 10 == 0 or done == len(missing):
                print(f"  {done}/{len(missing)}", file=sys.stderr)
    save_stage_cache(cache_path, cache)
    return cache


def apply_stage_to_rows(
    base_rows: list[dict],
    stage: StageSpec,
    *,
    matrix_agg: str,
    cache: dict,
) -> tuple[list[dict], int, int]:
    if not stage.needs_taskruns:
        return deepcopy(base_rows), len(base_rows), 0

    enriched: list[dict] = []
    ok = missing = 0
    for row in base_rows:
        entry = cache.get(f"tridx|{row['name']}") or {}
        records = entry.get("records")
        if not records:
            missing += 1
            continue
        platform_durs = stage_platform_durs_from_index(records, stage)
        if not platform_durs:
            missing += 1
            continue
        for platform, dur in aggregate_matrix(platform_durs, matrix_agg):
            new_row = dict(row)
            new_row["duration_min"] = dur
            new_row["platform"] = platform
            if platform and matrix_agg == "each":
                new_row["component"] = f"{row['component']}@{platform}"
            enriched.append(new_row)
            ok += 1
    enriched.sort(key=lambda r: r["completion"])
    return enriched, ok, missing


def summarize(rows: list[dict]) -> list[dict]:
    by_comp: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_comp[row["component"]].append(row["duration_min"])
    summary = []
    for component, vals in sorted(by_comp.items(), key=lambda kv: -statistics.median(kv[1])):
        vals_sorted = sorted(vals)
        p95_idx = min(len(vals_sorted) - 1, max(0, int(round(0.95 * (len(vals_sorted) - 1)))))
        summary.append(
            {
                "component": component,
                "n": len(vals),
                "median_min": statistics.median(vals),
                "p95_min": vals_sorted[p95_idx],
                "min_min": vals_sorted[0],
                "max_min": vals_sorted[-1],
            }
        )
    return summary


def write_csv(path: Path, rows: list[dict], *, stage: str) -> None:
    fields = [
        "stage",
        "completion",
        "duration_min",
        "component",
        "platform",
        "cluster",
        "branch",
        "event_type",
        "application",
        "sha",
        "name",
        "source",
        "ui_url",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{k: row.get(k, "") for k in fields if k != "stage"},
                    "stage": stage,
                    "completion": row["completion"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "duration_min": f"{row['duration_min']:.2f}",
                }
            )


def _short_component(name: str) -> str:
    s = name
    s = re.sub(r"^odh-", "", s)
    s = re.sub(r"-py312(-ubi9)?@", "@", s)
    s = re.sub(r"-py312(-ubi9)?$", "", s)
    s = re.sub(r"-v\d+(-\d+)*(-ea-\d+)?@", "@", s)
    s = re.sub(r"-v\d+(-\d+)*(-ea-\d+)?$", "", s)
    return s


def _stage_payload(rows: list[dict], summary: list[dict]) -> dict:
    by_comp: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_comp[row["component"]].append(row)
    order = [s["component"] for s in summary]
    traces = []
    for component in order:
        pts = by_comp[component]
        traces.append(
            {
                "x": [p["completion"].strftime("%Y-%m-%dT%H:%M:%SZ") for p in pts],
                "y": [round(p["duration_min"], 2) for p in pts],
                "text": [
                    (
                        f"{p['name']}<br>"
                        f"{p['event_type']} @ {p['branch']}"
                        + (f"<br>platform {p['platform']}" if p.get("platform") else "")
                        + f"<br>{p['duration_min']:.1f} min · sha {p['sha']}<br>"
                        f"{p['cluster']}/{p['source']}"
                    )
                    for p in pts
                ],
                "name": _short_component(component),
                "full_name": component,
                "mode": "lines+markers",
                "type": "scatter",
                "hovertemplate": "%{text}<extra></extra>",
            }
        )
    return {
        "traces": traces,
        "summary": summary,
        "n_points": len(rows),
        "n_series": len(by_comp),
    }


def write_html(
    path: Path,
    stages: dict[str, dict],
    *,
    default_stage: str,
    source_label: str,
) -> None:
    """stages: stage_key -> payload from _stage_payload (+ label)."""
    payload = {
        "defaultStage": default_stage,
        "source": source_label,
        "stages": stages,
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Konflux build durations by component</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{ font-family: ui-sans-serif, system-ui, sans-serif; color: #1a1a1a; }}
    body {{ margin: 1.5rem; max-width: 1200px; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 0.25rem; }}
    .meta {{ color: #555; font-size: 0.9rem; margin-bottom: 1rem; }}
    #controls {{ display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem; align-items: flex-end; margin-bottom: 0.75rem; }}
    #controls label {{ font-size: 0.85rem; display: block; }}
    #stage-select {{ min-width: 12rem; padding: 0.25rem 0.4rem; }}
    #component-filter {{ min-width: 280px; min-height: 8rem; }}
    #chart {{ width: 100%; height: 640px; border: 1px solid #ddd; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin-top: 1.5rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.35rem 0.5rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
    code {{ font-size: 0.8rem; }}
    .btn-row {{ display: flex; gap: 0.5rem; align-items: center; }}
  </style>
</head>
<body>
  <h1 id="title">Konflux build durations by component</h1>
  <p class="meta" id="meta"></p>
  <div id="controls">
    <label>Stage<br/>
      <select id="stage-select"></select>
    </label>
    <label>Components (multi-select)<br/>
      <select id="component-filter" multiple></select>
    </label>
    <div class="btn-row">
      <button type="button" id="select-all">All</button>
      <button type="button" id="select-none">None</button>
      <button type="button" id="select-slowest">10 slowest (median)</button>
    </div>
  </div>
  <div id="chart"></div>
  <h2>Summary (median-sorted)</h2>
  <table>
    <thead>
      <tr>
        <th>Component</th><th>n</th><th>Median (min)</th>
        <th>p95 (min)</th><th>Min</th><th>Max</th>
      </tr>
    </thead>
    <tbody id="summary-body"></tbody>
  </table>
  <script>
    const DATA = {json.dumps(payload)};
    const stageSelect = document.getElementById('stage-select');
    const filter = document.getElementById('component-filter');
    const meta = document.getElementById('meta');
    const titleEl = document.getElementById('title');
    const summaryBody = document.getElementById('summary-body');

    Object.keys(DATA.stages).forEach(key => {{
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = DATA.stages[key].label || key;
      if (key === DATA.defaultStage) opt.selected = true;
      stageSelect.appendChild(opt);
    }});

    function currentStage() {{
      return DATA.stages[stageSelect.value];
    }}

    function rebuildComponentFilter() {{
      filter.innerHTML = '';
      const stage = currentStage();
      const selectAll = stage.traces.length <= 12;
      stage.traces.forEach((t, i) => {{
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = t.name + ' (' + t.x.length + ')';
        // Few series: show all. Many: default to 10 slowest (already median-sorted).
        opt.selected = selectAll || i < 10;
        filter.appendChild(opt);
      }});
    }}

    function renderSummary() {{
      const stage = currentStage();
      summaryBody.innerHTML = '';
      (stage.summary || []).forEach(s => {{
        const tr = document.createElement('tr');
        tr.innerHTML = '<td><code>' + s.component + '</code></td>'
          + '<td>' + s.n + '</td>'
          + '<td>' + s.median_min.toFixed(1) + '</td>'
          + '<td>' + s.p95_min.toFixed(1) + '</td>'
          + '<td>' + s.min_min.toFixed(1) + '</td>'
          + '<td>' + s.max_min.toFixed(1) + '</td>';
        summaryBody.appendChild(tr);
      }});
    }}

    function draw() {{
      const stage = currentStage();
      const idxs = Array.from(filter.selectedOptions).map(o => Number(o.value));
      const traces = idxs.map(i => stage.traces[i]).filter(Boolean);
      titleEl.textContent = stage.title;
      meta.textContent = DATA.source + ' · stage=' + stageSelect.value
        + ' · ' + stage.n_points + ' points · ' + stage.n_series + ' series'
        + ' · showing ' + traces.length;
      const layout = {{
        title: {{ text: stage.title, font: {{ size: 14 }} }},
        xaxis: {{ title: 'Completion time (UTC)', type: 'date' }},
        yaxis: {{ title: 'Duration (minutes)', rangemode: 'tozero' }},
        legend: {{ orientation: 'v', tracegroupgap: 2 }},
        margin: {{ t: 48, r: 20, b: 56, l: 64 }},
        hovermode: 'closest',
      }};
      Plotly.newPlot('chart', traces, layout, {{responsive: true, displayModeBar: true}});
    }}

    function onStageChange() {{
      rebuildComponentFilter();
      renderSummary();
      draw();
    }}

    document.getElementById('select-all').onclick = () => {{
      Array.from(filter.options).forEach(o => {{ o.selected = true; }});
      draw();
    }};
    document.getElementById('select-none').onclick = () => {{
      Array.from(filter.options).forEach(o => {{ o.selected = false; }});
      draw();
    }};
    document.getElementById('select-slowest').onclick = () => {{
      Array.from(filter.options).forEach((o, i) => {{ o.selected = i < 10; }});
      draw();
    }};
    stageSelect.onchange = onStageChange;
    filter.onchange = draw;
    onStageChange();
  </script>
</body>
</html>
"""
    path.write_text(html)


def stage_label(stage: StageSpec) -> str:
    if stage.key == "pipeline":
        return "pipeline (full PipelineRun)"
    if stage.step_names:
        return f"{stage.key} ({'+'.join(stage.step_names)})"
    if stage.task_name:
        return f"{stage.key} (task {stage.task_name})"
    return stage.key


def stage_title(stage: StageSpec) -> str:
    if stage.key == "pipeline":
        return "Konflux successful PipelineRun duration by component"
    return f"Konflux successful {stage.key} duration by component"


def build_arg_parser() -> argparse.ArgumentParser:
    presets = ", ".join(sorted(STAGE_PRESETS))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "-i",
        "--input",
        type=Path,
        default=HERE / "data.json",
        help="Path to waterfall data.json (default: ./data.json)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=HERE / "durations.html",
        help="Output HTML path (default: ./durations.html)",
    )
    p.add_argument("--csv", type=Path, help="Also write rows for the default stage as CSV")
    p.add_argument(
        "--stage",
        action="append",
        dest="stages",
        help=(
            f"Stage to include (repeatable). Default: {', '.join(DEFAULT_UI_STAGES)}. "
            f"Presets: {presets}. Or task / task:step."
        ),
    )
    p.add_argument(
        "--matrix-agg",
        choices=("max", "sum", "each"),
        default="max",
        help=(
            "How to combine multi-arch build-images TaskRuns "
            "(default: max = wall-clock; sum; each = one series point per platform)"
        ),
    )
    p.add_argument(
        "--stage-cache",
        type=Path,
        default=HERE / "stage_cache.json",
        help="Cache of TaskRun timings (default: ./stage_cache.json)",
    )
    p.add_argument(
        "--cluster",
        action="append",
        dest="clusters",
        choices=("odh", "rhds"),
        help="Limit to cluster (repeatable)",
    )
    p.add_argument(
        "--event-type",
        action="append",
        dest="event_types",
        help="Limit to event type, e.g. push / pull_request (repeatable)",
    )
    p.add_argument(
        "--branch",
        action="append",
        dest="branches",
        help="Limit to target branch (repeatable)",
    )
    p.add_argument(
        "--component",
        action="append",
        dest="components",
        default=[],
        help="Substring filter on component name (repeatable, OR)",
    )
    p.add_argument("--days", type=int, help="Only runs completed within the last N days")
    p.add_argument(
        "--since",
        help="Only runs completed on/after this UTC timestamp (ISO-8601)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.input.is_file():
        print(
            f"error: {args.input} not found — run collect.py first "
            f"(see feat/ci-waterfall-dashboard:ci/waterfall/)",
            file=sys.stderr,
        )
        return 1

    stage_keys = args.stages or list(DEFAULT_UI_STAGES)
    try:
        stages = [parse_stage(s) for s in stage_keys]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Preserve order, drop duplicate keys
    seen: set[str] = set()
    uniq_stages: list[StageSpec] = []
    for stage in stages:
        if stage.key in seen:
            continue
        seen.add(stage.key)
        uniq_stages.append(stage)
    stages = uniq_stages

    since: datetime | None = None
    if args.since:
        since = parse_ts(args.since)
        if since is None:
            print(f"error: bad --since {args.since!r}", file=sys.stderr)
            return 2
    elif args.days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

    runs = load_runs(args.input)
    base_rows = filter_successful_runs(
        runs,
        clusters=set(args.clusters) if args.clusters else None,
        event_types=set(args.event_types) if args.event_types else None,
        branches=set(args.branches) if args.branches else None,
        component_substrings=args.components,
        since=since,
    )
    if not base_rows:
        print("error: no successful runs matched filters", file=sys.stderr)
        return 3

    needs_tr = any(s.needs_taskruns for s in stages)
    cache: dict = {}
    if needs_tr:
        contexts: dict[str, str] = {}
        for cluster in {r["cluster"] for r in base_rows}:
            cfg = CLUSTER_NS.get(cluster)
            if not cfg:
                continue
            ctx = get_oc_context(cfg["context_grep"])
            if not ctx:
                print(
                    f"error: no oc context matching {cfg['context_grep']!r} for cluster {cluster}",
                    file=sys.stderr,
                )
                return 4
            contexts[cluster] = ctx
        cache = ensure_taskrun_indexes(
            base_rows,
            cache_path=args.stage_cache,
            contexts=contexts,
        )

    stage_payloads: dict[str, dict] = {}
    default_rows: list[dict] | None = None
    default_summary: list[dict] | None = None
    for stage in stages:
        rows, ok, missing = apply_stage_to_rows(
            base_rows,
            stage,
            matrix_agg=args.matrix_agg,
            cache=cache,
        )
        if stage.needs_taskruns:
            print(
                f"stage={stage.key}: {ok} points, {missing} PipelineRuns without timing",
                file=sys.stderr,
            )
        if not rows:
            print(f"warning: skipping empty stage {stage.key}", file=sys.stderr)
            continue
        summary = summarize(rows)
        payload = _stage_payload(rows, summary)
        payload["label"] = stage_label(stage)
        payload["title"] = stage_title(stage)
        stage_payloads[stage.key] = payload
        if default_rows is None:
            default_rows = rows
            default_summary = summary

    if not stage_payloads:
        print("error: no stage data produced (check oc login / kubectl ka)", file=sys.stderr)
        return 5

    default_stage = next(iter(stage_payloads))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    filters = [f"stages={','.join(stage_payloads)}"]
    if needs_tr:
        filters.append(f"matrix-agg={args.matrix_agg}")
    if args.clusters:
        filters.append("cluster=" + ",".join(args.clusters))
    if args.event_types:
        filters.append("event=" + ",".join(args.event_types))
    if args.branches:
        filters.append("branch=" + ",".join(args.branches))
    if args.components:
        filters.append("component~" + "|".join(args.components))
    if since:
        filters.append("since=" + since.strftime("%Y-%m-%d"))
    source_label = f"Source: {args.input.name} · generated {generated} · " + "; ".join(filters)

    write_html(
        args.output,
        stage_payloads,
        default_stage=default_stage,
        source_label=source_label,
    )
    print(
        f"wrote {args.output} "
        f"({len(stage_payloads)} stages, default={default_stage}, "
        f"{len(base_rows)} PipelineRuns)"
    )

    if args.csv and default_rows is not None:
        write_csv(args.csv, default_rows, stage=default_stage)
        print(f"wrote {args.csv}")

    assert default_summary is not None
    print(f"\nSlowest medians for default stage={default_stage} (min):")
    for s in default_summary[:10]:
        print(f"  {s['median_min']:6.1f}  n={s['n']:3d}  {s['component']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
