# AI Agents Guide — Workbench Build Waterfall

Local prototype dashboard for Konflux workbench + runtime image builds (`ci/waterfall/`).

**Docs:** [SPEC.md](SPEC.md) (spec), [README.md](README.md) (quick start), [BUGS.md](BUGS.md) (bug catalog) — all must stay current; see [AGENTS.md](AGENTS.md).

## Documentation maintenance (required)

**After every change** to behavior, workflow, or known issues in this directory, **update every affected markdown file in the same PR/commit**. Do not leave docs stale while code moves on.

A change is **not done** until the docs below reflect it.

| File | Update when |
|------|-------------|
| [SPEC.md](SPEC.md) | Collector, UI, `data.json` schema, tracked streams, merge rules, limits, operator workflow — the **as-implemented** truth |
| [README.md](README.md) | Quick start, commands, prerequisites, or high-level “how to run” steps change |
| [BUGS.md](BUGS.md) | A bug is fixed (`WF-###` under Fixed) or a known issue is found/closed (`WF-1xx` under Known open) |
| [PERFORMANCE.md](PERFORMANCE.md) | Collection runtime, API load, or output-size observations change; append a dated row after re-measuring |
| [AGENTS.md](AGENTS.md) | Agent rules, file map, design constraints, or this maintenance policy itself changes |

### Per-file rules

**SPEC.md**
- Edit the matching section for any behavior change; do not leave contradictory prose.
- New limitations → §9 (Limitations). Removed features → delete or mark deprecated.
- Future ideas only in §11 (Future work) — keep SPEC factual.

**README.md**
- Keep it short: entry point for humans, not a duplicate of SPEC.
- If SPEC gains a new prerequisite or command, README must mention it.

**BUGS.md**
- Fixed bug → new row in Fixed bugs; remove from Known open if listed there.
- Diagnosed but unfixed → add/update Known open with symptom, cause, and fix direction.

**AGENTS.md**
- If you add a new file under `ci/waterfall/` or change what agents must/must not do, update this guide.

## Files

| File | Role |
|------|------|
| [SPEC.md](SPEC.md) | As-implemented system spec (keep current) |
| [BUGS.md](BUGS.md) | Fixed-bug catalog + known open issues (keep current) |
| [PERFORMANCE.md](PERFORMANCE.md) | Collection timing and load observations (point in time) |
| [AGENTS.md](AGENTS.md) | Agent rules; keep all `*.md` here in sync with code |
| [README.md](README.md) | Quick start for humans (keep current) |
| [collect.py](collect.py) | `oc` + KubeArchive collector → `data.json` |
| [index.html](index.html) | Latest-status matrix UI |
| [waterfall.html](waterfall.html) | Buildbot-style timeline waterfall UI |
| `data.json` | Generated snapshot (local; not committed) |

## Commands

```bash
cd ci/waterfall
python3 collect.py          # refresh data.json
python3 -m http.server 8888   # http://localhost:8888
```

Requires: `oc` (both clusters), `kubectl-ka`, VPN for RHDS.

## Design constraints

- **Do not** add Tekton Results or broad Prometheus polling — [KFLUXSPRT-8417](https://redhat.atlassian.net/browse/KFLUXSPRT-8417).
- **Do not** use application-only KubeArchive queries (100-result cap hides workbench history on busy streams like `rhoai-v2-25`); use **component label selectors** from `NOTEBOOK_COMPONENT_STEMS` (see SPEC §4.4).
- **Do not** expand RHDS streams without explicit request; keep ancient `rhoai-v2-*` apps out.
- Scope: notebooks-team workbench/runtime images only; exclude operator/controller components.

## Related docs

- [PERFORMANCE.md](PERFORMANCE.md) — collection runtime and API load (point-in-time observations)
- [guide/docs/notebooks/konflux/kubearchive.md](../../guide/docs/notebooks/konflux/kubearchive.md)
- [guide/docs/notebooks/konflux/rhoai-monitoring-o11y.md](../../guide/docs/notebooks/konflux/rhoai-monitoring-o11y.md)
- Repo root [AGENTS.md](../../AGENTS.md)
