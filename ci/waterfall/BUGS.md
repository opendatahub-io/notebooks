# Workbench Build Waterfall — Bug Catalog

Chronicle of bugs found and fixed while building the prototype in `ci/waterfall/`.
Session: **2026-07-28**.

A **bug** here is anything the operator wanted changed, or anything implemented incorrectly and then corrected.

When you fix a new bug, append a row to [Fixed bugs](#fixed-bugs) (next `WF-###` id) and move any resolved item out of [Known open](#known-open-not-fixed-yet).

Related: [SPEC.md](SPEC.md) (as-implemented behavior), [AGENTS.md](AGENTS.md) (keep SPEC in sync).

---

## Fixed bugs

| ID | Symptom | Root cause | Fix | Files |
|----|---------|------------|-----|-------|
| **WF-001** | Matrix cells not clickable | Prometheus rows had no `ui_url`; PR builds were skipped in the UI loop; link was nested inside the cell instead of the cell being the link | Generate `konfluxUrl()` for all sources; stop filtering `pull_request` events; render each cell as `<a class="cell">` | `index.html` |
| **WF-002** | ODH `PR@main` row missing | Live ODH runs are almost all PR builds; collector/UI excluded `event_type === pull_request'` | Include PR builds; label rows `PR@{branch}` | `index.html` |
| **WF-003** | RHDS Konflux links 404 (e.g. `minimal-cuda-py312` without suffix) | Prometheus reports base component names; Konflux UI expects versioned names (`…-py312-v3-3`) | `konfluxUrl()` appends application version suffix on `stone-prod-p02` (`rhoai-v3-3` → `-v3-3`) | `index.html` |
| **WF-004** | Dashboard showed ~10 components, not ~18 | Initial scope was workbench-only; `llmcompressor` uses truncated `odh-wb-` prefix | Expand catalog to 11 workbenches + 7 pipeline runtimes; collector matches `odh-wb-` and `odh-pipeline-runtime-` | `index.html`, `collect.py` |
| **WF-005** | `codeserver-cpu` column empty / wrong | Regex order: generic `minimal-cpu` / `datascience-cpu` matched `codeserver-datascience-cpu` and runtime names first | Ordered patterns: `rt-*` and `codeserver-cpu` before generic workbench patterns; tightened workbench regexes to require `jupyter-` / `wb-jupyter-` | `index.html` |
| **WF-006** | All 7 runtime columns missing or mis-bucketed | Same as WF-005: `pipeline-runtime-minimal-cpu` matched workbench `minimal-cpu` | Same pattern-order fix; fixed `COMPONENT_ORDER` column sort | `index.html` |
| **WF-007** | `workbenches-operator` / `workbenches-controller` rows appeared | Out of scope for notebooks repo; matched broad `workbench` substring | Exclude via `EXCLUDED_COMPONENT_RE` in collector; `shortComponent()` returns `null` in UI | `collect.py`, `index.html` |
| **WF-008** | `trustyai` on `rhoai-2.25` showed **failed**; Konflux UI showed **Succeeded** | `rhoai-monitoring` Prometheus exporter disabled Jul 2026 ([KFLUXSPRT-8417](https://redhat.atlassian.net/browse/KFLUXSPRT-8417)); dashboard showed Jul 14 stale `konflux_pipeline_success=0` | First: stale-Prometheus UI (`~` / `stale` class). **Final:** remove Prometheus from collector entirely; use `oc` + KubeArchive only | `collect.py`, `index.html` |
| **WF-009** | `rhoai-3.6-ea.1` row sparse then **vanished** | Live PipelineRuns GC'd after completion; Prometheus never had 3.6 metrics; collector was live-only | Add KubeArchive archived PipelineRun fallback; merge `live` + `archived` (live wins) | `collect.py`, `index.html` |
| **WF-010** | `collect.py` hung / overloaded Konflux (~400+ KA calls) | First KubeArchive implementation queried **per component** (every Component CR × KA) | One `kubectl ka get` **per application** (not per component); ~8 calls total | `collect.py` |
| **WF-011** | Collector warned on ancient apps (`rhoai-v2-13`, …) and was slow | RHDS apps auto-discovered via `oc get applications` (`rhoai-v*`) | Fixed allowlist: `rhoai-v2-25`, `rhoai-v3-3`, `rhoai-v3-4`, `rhoai-v3-5`, `rhoai-v3-6-ea-1` only | `collect.py` |
| **WF-012** | `main` and `PR@main` collapsed into one row | Merge key was `(component, branch)` only | `merge_key()` uses `PR@{branch}` for `pull_request` events | `collect.py` |
| **WF-013** | ODH/RHDS rows outside supported streams (`stable`, old 2.x, etc.) | No branch filter on live or archived entries | `TRACKED_RHDS_BRANCHES` / `ODH_TRACKED_BRANCHES` + `branch_tracked()` filter | `collect.py` |
| **WF-014** | Collector timed out on slow KubeArchive / cluster API | Timeouts were 60s (`oc`) / 90s (`ka`) | Generous bounded timeouts: `oc` 180s, `ka` 600s per app, context lookup 30s; `TimeoutExpired` → warn and continue | `collect.py`, `SPEC.md` |
| **WF-015** | `ui_url` pointed at wrong Konflux path for live runs | Early collector built pipelinerun URLs with guessed application names | Standardize on component **activity** URL from PipelineRun labels | `collect.py` |
| **WF-016** | `rhoai-2.25` row very sparse (few cells) | Application-wide KA query hits 100-result cap; newest 100 are operator/FBC, zero workbench after filter | KubeArchive queries use `appstudio.openshift.io/component=<name>` per canonical stem × stream suffix (parallel, bounded) | `collect.py`, `SPEC.md` |
| **WF-017** | Matrix showed only latest status per cell; no Buildbot-style timeline | Collector emitted one row per component×branch; UI was matrix-only | Add `pipelinerun_history` (up to 50 runs per key) in `collect.py`; new `waterfall.html` timeline (columns = components, time vertical, colored bars) | `collect.py`, `waterfall.html`, `SPEC.md` |
| **WF-018** | UI subtitle still mentioned Prometheus | Copy not updated when collector dropped Prometheus | Subtitle now says `oc + KubeArchive`; links to timeline view | `index.html` |

### WF-008 / WF-009 detail (data-source arc)

The prototype went through three data-source iterations in one session:

1. **Prometheus only** (+ thin live `oc`) — fast but wrong for 3.6 and stale for 2.25.
2. **Prometheus + stale indicator** — surfaced the problem but did not fix root cause.
3. **`oc` + KubeArchive, Prometheus off** — current design (see [SPEC.md §4](SPEC.md)).

---

## Known open (not fixed yet)

| ID | Symptom | Root cause | Notes |
|----|---------|------------|-------|
| **WF-103** | Archived tooltips rarely show | UI hardcodes `source: 'live'` when reading `live_pipelineruns` instead of `run.source` | `index.html` — see SPEC §6 |
| **WF-104** | Version/branch filter ignored for matrix rows | `renderWaterfall()` filters Prometheus entries but not `live_pipelineruns` | `index.html` — see SPEC §6 |

---

## How to use this file

1. **Reproduce** — note cluster, branch, and whether live vs archived.
2. **Fix** — minimal change; update [SPEC.md](SPEC.md) in the same commit.
3. **Record** — add a **WF-###** row under Fixed bugs; link the commit or PR if applicable.
4. **Close** — remove matching row from Known open.
