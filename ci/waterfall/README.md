# Notebooks Workbench Build Waterfall

Buildbot-style waterfall view for ODH and RHDS workbench image builds.

**Docs:** [SPEC.md](SPEC.md), [README.md](README.md), [BUGS.md](BUGS.md), [PERFORMANCE.md](PERFORMANCE.md), [AGENTS.md](AGENTS.md) — keep all in sync with code (see AGENTS.md).

## Quick start

```bash
# Collect data (requires oc login to both clusters + VPN for RHDS; kubectl-ka plugin)
python3 collect.py

# Serve locally
python3 -m http.server 8888

# Open matrix (latest status per cell)
open http://localhost:8888/

# Timeline waterfall (Buildbot-style)
open http://localhost:8888/waterfall.html
```

## Data sources

**Prometheus is not used** — the `rhoai-monitoring` Tekton Results exporter has been disabled since Jul 2026 ([KFLUXSPRT-8417](https://redhat.atlassian.net/browse/KFLUXSPRT-8417)).

`collect.py` uses a **low-load** strategy (no broad Results API polling):

| Call | Per cluster | Purpose |
|------|-------------|---------|
| `oc get pipelinerun -l type=build` | 1 | Live / in-flight builds |
| `kubectl ka get pipelinerun -l component=…,type=build` | 18 (ODH) or 95 (RHDS) | Archived builds per workbench/runtime component |

KubeArchive uses **component label selectors** (not application-wide lists) so workbench history is not buried behind operator/FBC runs in the 100-result cap.

**Tracked streams only:**

| Cluster | KubeArchive applications | Branches kept |
|---------|--------------------------|---------------|
| ODH | `opendatahub-builds` | `main`, `PR@main` |
| RHDS | `rhoai-v2-25`, `rhoai-v3-3`, `rhoai-v3-4`, `rhoai-v3-5`, `rhoai-v3-6-ea-1` | matching `rhoai-2.25` … `rhoai-3.6-ea.1` |

Ancient RHDS apps (`rhoai-v2-13`, etc.) are not queried.

## What it shows

**Matrix** (`index.html`): rows = branches, columns = components, one latest-status cell each.

**Timeline waterfall** (`waterfall.html`): [Buildbot waterfall](https://docs.buildbot.net/latest/manual/configuration/www/ui/waterfall_view.html) — pick a branch; columns = components; vertical axis = time (newest at top); colored bars = individual PipelineRuns; dashed bands = same-SHA build waves.

Both views:
- Cell color: green (success), red (failed), yellow (running), grey (unknown)
- Tooltips note KubeArchive-sourced cells (GC'd from live cluster)
- Filters: cluster, branch, status

## Requirements

- `oc` logged into `stone-prd-rh01` and `stone-prod-p02`
- `kubectl-ka` plugin (`kubectl ka`)
- VPN for RHDS cluster
