# Bodies of Water: Notebooks Troubleshooting Guide

Companion to [bodies-of-water.md](bodies-of-water.md): symptom → cause → fix for the
Stream → Lake → Ocean flow of the Notebooks component (ODH `main` → `stable` for the ODH
deliverable; ODH `main` → RHDS `main` → RHOAI trains for the product).

## Quick table

| Symptom | Most likely cause | Fix |
|---|---|---|
| Change on `main` never appears on a RHOAI train | Train divergence: auto-merge targets only the **newest** onboarded train | Cherry-pick downward by hand — [procedure](bodies-of-water.md#how-to-cherry-pick-downward-cleanly) |
| Fast-forward `main` → `stable` GHA fails | `stable` is not an ancestor of `main` (direct commits/merges landed on `stable`) | Identify what landed on `stable` and why; **cherry-pick those fixes onto `main`**, then **force-push `main` to `stable`** so `stable` tracks `main` again; prevent by never committing to `stable` directly |
| ODH nightly build fails but `main` PR was green | `stable` picked up a commit whose gates ran against different base/lockfiles, or a nightly-only code path | Triage the Konflux PipelineRun for `stable`; fix on `main` and re-promote — do not hotfix `stable` |
| Build passes on `main`, fails on an older RHOAI train | Branch-locked dependencies (e.g. an rpm present in `main` lockfiles but not the train's, historically `libxkbfile-devel`) | Refresh that train's lockfiles (rpm/npm) — see [below](#build-failures-on-downstream-trains) |
| Same build fails intermittently in cachi2 with a corrupt npm tarball | Stale/corrupt cachi2 cache in the build pod | Clear the cache dir in the failing build stage (`cachi2/output/deps/npm`) and re-run |
| Push to a branch did not trigger any Konflux build | CEL `pathChanged()` guard, nudge-file mechanics, or the branch has no `*-push.yaml` | Check [konflux.md: Why pushing a branch may not trigger builds](konflux.md#why-pushing-a-branch-may-not-trigger-builds) and the "Known issues" section |
| Duplicate Konflux checks on RHDS PRs | Two integrations watching the same event | Expected in some windows; see [konflux.md: Duplicate Konflux checks](konflux.md#duplicate-konflux-checks-on-red-hat-data-servicesnotebooks-prs) |
| Merged PR does not reach the catalog (FBC fragment) | Nudge chain stall (operator→bundle→FBC) | Check the nudge PRs in `rhods-operator` / bundle / RHOAI-Build-Config repos; escalate to DevOps with the component build PipelineRun |
| ODH release image has the wrong tag | Tag format mistake (patch version included) or Update-Tekton-Tags PR not merged | Tags are `<train>-v<NN>` with **no patch version**; after publishing, merge the "Update Tekton Tags" PR promptly |
| Commented a release on a closed/previous tracker | Trackers are **per-release-cycle** — each `[Release Tracker]` issue is closed when its cycle ends | Use the *current* `[Release Tracker]` issue in [opendatahub-io/opendatahub-community](https://github.com/opendatahub-io/opendatahub-community/issues) (e.g. `#203` for 3.6.0-EA2); remove the wrong comment |

## Sync failures (DevOps auto-sync: ODH `main` → RHDS `main` → train)

The sync is two hops, both GitHub Actions in
[`red-hat-data-services/rhods-devops-infra`](https://github.com/red-hat-data-services/rhods-devops-infra)
(config: `upstream-source-map.yaml`, `main-release-source-map.yaml`); failures notify in Slack.

1. Open the failed sync run's logs; look for:
   `CONFLICT (content)`, `Automatic merge failed`, `Patch failed`.
2. Typical conflict causes:
   - midstream (`opendatahub-io`) modifications diverged from what the train already has,
   - downstream-only patches on the train overlap with our upstream change,
   - files we deleted or renamed upstream.
3. Resolve in our repo: make the train-side state reachable from ODH `main` (usually a
   follow-up PR on `main` adjusting the content), then ask DevOps to **re-run the
   sync** — do not push to RHDS `main` or the train yourself.

## Cherry-picking downward (older/frozen trains)

- **Never** merge a newer train into an older one (produces dirty PRs with foreign
  `.tekton/` PipelineRuns and tag retargets; GitHub cannot retarget a PR head — see the
  #2806 → #2807 episode in [bodies-of-water.md](bodies-of-water.md#train-divergence-the-important-rule)).
- Branch **from the older train**, cherry-pick product commits, keep `.tekton/` byte-identical
  to that train.
- Expect train-specific build fallout (branch-locked deps) and pre-empt it:
  - rpm side: compare the failing package's lockfile state between `main` and the train
    (`uv.lock.d/pylock.*.toml`, `dependencies/`); refresh via `make refresh-lock-files` on a
    branch cut from the train, with the train's base images.
  - npm side (code-server images): regenerate via
    `scripts/lockfile-generators/download-npm.sh` (it rewrites registry/git-resolved URLs in
    `package-lock.json`/`package.json`); if a tarball is corrupt, clear
    `cachi2/output/deps/npm` in the build first.

## Build failures on downstream trains

1. Identify the failing PipelineRun (GitHub PR/push check link → PipelineRun name).
2. Compare the **branch-locked inputs** of the train vs `main`:
   lockfiles (`uv.lock.d/`, `package-lock.json`), `build-args/*.conf` (pinned base-image
   digests), `versions_config.yml`.
3. Fix by refreshing the **train branch's** lockfiles/constraints — the fix must land on the
   train (cherry-pick procedure above), because the auto-sync will not carry it downward.
4. Known historical case: `libxkbfile-devel` present in `main`'s lockfile set but absent on
   the train, failing only the train's Konflux builds.

## Release process pitfalls

- **Tag format**: `<train>-v<NN>`, no patch version (e.g. `3.5-v1.47`, `3.6_ea1-v1.48`).
  The "Update Tekton Tags" GHA regex accepts both the legacy `YYYYa-vNN` and the new
  `X.Y(_eaN)?-vNN` forms, but it will fail if it cannot find *exactly one* previous tag in
  `.tekton/*.yaml` — check for stale leftovers first.
- **Ordering**: run "Update Tekton Tags" **after** "Create release" (the release must exist
  before the tag for the *next* cycle moves).
- **Tracker**: notebook releases are commented on the *current* per-cycle `[Release Tracker]`
  issue in [opendatahub-io/opendatahub-community](https://github.com/opendatahub-io/opendatahub-community/issues)
  (e.g. `#203` — 3.6.0-EA2; the EA1 cycle used `#202`, which is now closed).

## Escalation

| What | Where | Attach |
|---|---|---|
| Sync failure, train onboarding, RC/GA questions | RHOAI DevTestOps office hours (Tuesdays) or `#rhoai-devtestops-requests` (Slack) | Failed PipelineRun name + branch + the exact step that failed |
| Konflux trigger not firing | Same | Branch, commit SHA, expected vs observed checks on the PR/push |
| Nightly/RC broken by our image | Release channel for that train | RHOAI nightly build ID, failing Jenkins stage, local repro (`make test-integration PYTEST_ARGS="--image=<img>"`) |
| Strategy/phase questions (not a bug) | [RHOAIENG-28641](https://redhat.atlassian.net/browse/RHOAIENG-28641) (program outcome) / [RHAIENG-1273](https://redhat.atlassian.net/browse/RHAIENG-1273) (Notebooks adoption) | — |
