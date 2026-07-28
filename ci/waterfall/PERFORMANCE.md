# Workbench Build Waterfall — Collection Performance

Point-in-time observations of `collect.py` runtime, output size, and API load.
**Amend this file** when you re-measure after collector or environment changes.

Related: [SPEC.md §4](SPEC.md) (collector design), [BUGS.md](BUGS.md) (performance-related fixes WF-010, WF-014, WF-016).

---

## How to measure

```bash
cd ci/waterfall
/usr/bin/time -p python3 collect.py 2>&1 | tee /tmp/waterfall-collect.log
```

Record:

- Wall time (`real` from `time -p`)
- Stderr lines (`live PipelineRuns`, `merged`, `history`, `Wrote …`)
- `data.json` size (`ls -lh data.json`)
- Date, VPN, cluster load notes

`collect.py` does **not** yet emit per-cluster or per-phase timings; wall time is end-to-end only.

---

## Collection modes and depth knobs

These are the levers that change duration and payload (constants in `collect.py` unless noted).

| Knob | Default | Effect on runtime | Effect on output |
|------|---------|-------------------|------------------|
| **Clusters** | ODH + RHDS (both) | ~2× live `oc`; RHDS adds ~5× more KA queries than ODH | Both clusters in `data.json` |
| **RHDS applications** | 5 tracked (`rhoai-v2-25` … `rhoai-v3-6-ea-1`) | Each app adds 19 KA component queries (95 total RHDS) | More branch rows per component |
| **KA query shape** | Per-component label selector | vs application-wide: fewer calls but wrong/sparse data (WF-016) | vs per-`oc get components`: far fewer calls |
| **`KA_WORKERS`** | `8` | Parallel KA fan-out; higher → faster but more burst load on KubeArchive | None |
| **`HISTORY_MAX_PER_KEY`** | `50` | More archived runs fetched per query (KA returns up to 100); merge/cap is client-side | `pipelinerun_history` row count and JSON size |
| **`live_pipelineruns` only** | No (history always built) | Same API calls as full run; only JSON merge differs | Smaller `data.json` (no `pipelinerun_history`) |
| **Prometheus** | Off (removed Jul 2026) | Was ~1 HTTP query + parsing when enabled | `prometheus_metrics: []` |

**Current default mode:** `oc` live list + per-component KubeArchive, both clusters, matrix merge + timeline history (`HISTORY_MAX_PER_KEY=50`).

---

## Observations (point in time)

Environment unless noted: macOS, `oc` logged into ODH + RHDS, VPN for stone-prod-p02, collector as in repo at observation date.

### Summary table

| Date | Mode | Wall time | API calls (approx.) | Latest rows | History rows | `data.json` |
|------|------|-----------|---------------------|-------------|--------------|-------------|
| 2026-07-28 | Prometheus + `oc get components` + KA | **~20 min** | High (Prometheus + many component CR walks + KA) | — | — | ~292 KB |
| 2026-07-28 | `oc` + KA **per application** (22 RHDS apps, auto-discovery) | **~3 min** | ~2 live + ~24 KA | 71 | — | — |
| 2026-07-28 | `oc` + KA per app, **5 RHDS apps** allowlist | **~30 s** (informal) | ~2 live + ~8 KA | ~44 | — | — |
| 2026-07-28 | `oc` + **per-component KA** (`KA_WORKERS=8`), matrix only | **~2 min** | ~115 (2 + 113 KA) | 182 | — | ~144 KB |
| 2026-07-28 | Same + **`pipelinerun_history`** (`HISTORY_MAX_PER_KEY=50`) | **~1 min 43 s** (`103 s`) | ~115 (unchanged) | 182 | 5,019 | **~3.9 MB** |

Rows before 2026-07-28 are from the same prototype session (see [BUGS.md](BUGS.md)); timings are wall-clock from operator runs, not automated benchmarks.

### Latest run detail (2026-07-28, full history mode)

```
Collecting odh (arewm-tenant/api-stone-prd-rh01-pg1f-p1-openshiftapps-com:6443/jdanek)...
  live PipelineRuns: 10
  KubeArchive: 18/18 component(s) with archived builds
  merged: 36 component×branch entries
  history: 1562 timeline build(s)
Collecting rhds (ai-tenant/api-stone-prod-p02-hjvn-p1-openshiftapps-com:6443/jdanek)...
  live PipelineRuns: 5
  KubeArchive: 91/95 component(s) with archived builds
  merged: 146 component×branch entries
  history: 3457 timeline build(s)

Wrote data.json (4096187 bytes, 182 latest + 5019 history)
```

| Phase | ODH | RHDS | Notes |
|-------|-----|------|-------|
| Live `oc get pipelinerun` | 10 runs | 5 runs | Sub-second to low seconds (not timed separately) |
| KA component queries | 18 | 95 | Dominates wall time; 8 parallel workers |
| KA hit rate | 18/18 | 91/95 | 4 RHDS components returned no archived workbench runs |
| Merged (matrix) | 36 | 146 | One row per component×branch (incl. `PR@main`) |
| History (timeline) | 1,562 | 3,457 | Capped at 50 runs per component×branch key |

**Rough split:** RHDS is ~70% of KA queries and likely ~70–85% of wall time (more queries, VPN, busier archive).

---

## API load (current default)

Per full collect:

| Backend | Calls | Concurrency | Per-call behavior |
|---------|-------|-------------|-------------------|
| `oc get pipelinerun` | 2 | Serial (per cluster) | Labeled list; client filters to notebooks components |
| `kubectl ka get` | 113 (18 ODH + 95 RHDS) | Up to 8 | `type=build` + `component=<name>`; up to 100 archived runs each |
| **Total** | **~115** | Burst over ~1–3 min | No Tekton Results API, no Prometheus |

Compared to disabled `rhoai-monitoring` Tekton Results polling ([KFLUXSPRT-8417](https://redhat.atlassian.net/browse/KFLUXSPRT-8417)): this collector uses **narrow KubeArchive reads**, not hourly Results list scans across ~70 components × apps.

---

## Timeouts (upper bound if everything stalls)

| Constant | Value | Applies to |
|----------|-------|------------|
| `OC_TIMEOUT_SEC` | 180 s | Each live `oc get pipelinerun` |
| `KA_TIMEOUT_SEC` | 600 s | Each `kubectl ka get` (per component) |
| `OC_CONTEXT_TIMEOUT_SEC` | 30 s | `oc config get-contexts` |
| `KA_WORKERS` | 8 | Max parallel KA subprocesses |

Worst-case theoretical wall time is large (113 × 600 s if serialized and all time out); in practice runs complete in **~2–3 minutes** when KubeArchive is healthy.

---

## UI / serve (not collector)

| Step | Typical cost |
|------|----------------|
| `python3 -m http.server 8888` | Negligible |
| Browser load `data.json` (~4 MB) | Local; one-time fetch per refresh |
| `waterfall.html` render | Client-side; thousands of DOM bars on busy branches (e.g. `rhoai-3.4`) |

---

## Open questions / future measurements

- [ ] Per-cluster wall time (instrument `collect_cluster()`)
- [ ] Per-phase: live vs KA vs JSON write
- [ ] `HISTORY_MAX_PER_KEY` sweep: 10 / 25 / 50 / 100 vs JSON size (API calls unchanged; KA still returns up to 100)
- [ ] ODH-only or RHDS-only single-cluster mode (if added)
- [ ] Cold vs warm KubeArchive / VPN variance across days
- [ ] Scheduled collect on CI vs laptop

When you add a row to **Observations**, keep the old rows for comparison and note what changed in the collector or network.
