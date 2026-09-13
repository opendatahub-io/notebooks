# Bodies of Water: Notebooks Release Workflow

Notebooks' adoption of the **Bodies of Water** release strategy (Stream → Lake → Ocean) with
quality gates and explicit transition processes. This is the component-level workflow document
for the [Notebooks - Bodies of Water Adoption](https://redhat.atlassian.net/browse/RHAIENG-1273)
epic; companion troubleshooting guide: [bodies-of-water-troubleshooting.md](bodies-of-water-troubleshooting.md).

**Signoff:** Jiri Daněk, 2025-08-05 (row in the cross-team signoff table of the canonical
[Release Strategy – The Bodies Of Water](https://docs.google.com/document/d/1LXbAylu-1rCw1gkqNuhLoPC5tzD70gg0jdGy-SBgyYI/edit)
design doc). Phase status for the whole program: [RHOAIENG-28641](https://redhat.atlassian.net/browse/RHOAIENG-28641).

For the *mechanisms* (sync pipelines, Konflux builds, nudge chains, RC/GA promotion) see
[code-flow-odh-to-rhoai.md](code-flow-odh-to-rhoai.md). This document is the *team workflow*:
what we do, when, and where to escalate.

## The model

| Body of water | Meaning | Notebooks branch | Org | Built where |
|---|---|---|---|---|
| **Stream** | Component-owned development trunk | `main` | `opendatahub-io/notebooks` | — |
| **Lake** (ODH) | ODH stable, first joint deliverable | `stable` | `opendatahub-io/notebooks` | **ODH Nightly** (Konflux, `open-data-hub-tenant`) |
| **Ocean** (RHOAI) | RHOAI stable, product-releasable | `rhoai` → RHDS `main` → `rhoai-X.Y` train | `red-hat-data-services/notebooks` | **RHOAI Nightly** + **RC/GA** (Konflux, `rhoai-tenant`) |

```
opendatahub-io/notebooks                     red-hat-data-services/notebooks
  main        (Stream)                         main         (Ocean, DevOps-owned)
  stable      (Lake) ── ODH nightly build ──▶  rhoai-X.Y    (train, auto-synced from stable)
  2025a/…     (ODH GA release branches)                      └─ RHOAI nightly + RC/GA
```

## Branch strategy

### Branches and ownership

- **`main`** (Stream, this org): all development lands here first — features, fixes, CVEs.
- **`stable`** (Lake, this org): the ODH integration point. **ODH Nightly is built from
  `stable`** (see "ODH kickoff" below). Promoted from `main` only by fast-forward.
- **`2025a`, `2024b`, …** (ODH GA release branches, this org): cut per ODH release cycle;
  image tags for an ODH release are built from these.
- **RHDS `main`** (Ocean, **DevOps-owned**): receives `stable` via DevOps auto-sync; we do not
  commit here directly.
- **RHDS `rhoai-X.Y`** (train, DevOps-managed): e.g. `rhoai-3.6-ea.1`, `rhoai-3.6-ea.2`.
  RHOAI Nightlies and RC/GA builds run from these.

### Train divergence (the important rule)

DevOps auto-merge from `stable` targets **only the newest onboarded train**. When a new train is
onboarded (e.g. `rhoai-3.6-ea.2`), auto-merge is switched to it and **stops for older trains**
(e.g. `rhoai-3.6-ea.1`) so next-release work on `main` cannot leak into a frozen train.

Consequences:

- Work merged to `main`/`stable` after the cut reaches only the **newest** train automatically.
- Anything still needed on an **older** train must be **cherry-picked downward by us** —
  DevOps does not do this.
- First real occurrence: the 2026-08-24 EA1/EA2 onboarding. EA1-targeted work that landed on
  `main` after the cut was delivered by a *new branch cut from `rhoai-3.6-ea.1`* with the
  commits cherry-picked and `.tekton/` left identical to that train
  ([red-hat-data-services/notebooks#2807](https://github.com/red-hat-data-services/notebooks/pull/2807));
  a dirty EA2→EA1 merge PR (#2806) was closed because GitHub cannot retarget a PR head.

#### How to cherry-pick downward cleanly

1. Create a branch **from the older train** (never merge a newer train into it).
2. Cherry-pick only the product commits (Dockerfiles, lockfiles, `ci/`, `scripts/`, `manifests/`).
3. **Leave `.tekton/` exactly as the older train has it** — PipelineRuns are synced per-branch
   from konflux-central and differ between trains; copying them is what makes merges dirty.
4. Open the PR against the older train; it needs review + approve before freeze.
5. Verify builds green on the train (see [troubleshooting](bodies-of-water-troubleshooting.md#build-failures-on-downstream-trains)).

## Quality gates and transition criteria

| Transition | Mechanism | Gates that must be green |
|---|---|---|
| PR → `main` (Stream) | PR to `opendatahub-io/notebooks`, merged via Prow/Tide (`/lgtm` `/approve`); merge bot `openshift-merge-bot[bot]` | Code-quality GHAs (`.github/workflows/code-quality.yaml`), unit tests, container integration tests (testcontainers), Konflux PR builds for changed images. Full catalog: [docs/agents/testing.md](agents/testing.md) |
| `main` → `stable` (Stream → Lake) | **"Merge main into stable (fast-forward only)"** GHA (`.github/workflows/merge-main-to-stable-fast-forward.yaml`); use `dry_run: true` to verify | `stable` must be an ancestor of `main` (pure fast-forward). Then the ODH nightly gate: ODH nightly build + smoke/ITS tests pass against it (see below) |
| `stable` → RHOAI train (Lake → Ocean) | DevOps auto-sync (`rhods-devops-infra` GitHub Actions; configmaps in that repo) | RHOAI nightly build from the train + product-level E2E on Jenkins (ods-ci `0500__ide` + opendatahub-tests against the nightly) |
| Nightly → RC/GA | **DevOps-owned** (Stage Promoter, release CRs, image mirroring) — see code-flow doc §9 | Component team role: keep the train green; do not block on our side |

### ODH nightly

- Built from `stable` by Konflux (`open-data-hub-tenant`), images tagged `odh-stable`-style
  (no date; branch/SHA/`-nightly` conventions — code-flow doc §4).
- Release kickoff: **`make kickoff-release`** (driven from `versions_config.yml`, opens a PR;
  the **"Release Kickoff Action"** GHA in `.github/workflows/release-kickoff.yaml` automates
  override + run + PR).
- Smoke against the build: the odh-nightly Jenkins job runs ods-ci smokes; the on-demand ITS
  scenario is `its-trigger-nightly`.

### RHOAI nightly

- Built from the RHDS train branch (scheduled Konflux pipelines), images tagged
  `rhoai-X.Y` / `rhoai-X.Y-<sha>` / `rhoai-X.Y-nightly`.
- Jenkins runs tier1/2/3 sanity + smoke against `rhoai-fbc-fragment:rhoai-X.Y-nightly`.
- Our workbench/runtime images are consumed by the operator → bundle → FBC-fragment nudge chain
  (code-flow doc §6): a green train build cascades into the catalog automatically.

## Testing at each stage

Full catalog (targets, markers, CI parity): **[docs/agents/testing.md](agents/testing.md)**.

| Stage | What runs | How |
|---|---|---|
| Local | Static + unit + doctests + Go tests | `make test`, `make test-unit` |
| Local / PR | Container integration tests | `make test-integration PYTEST_ARGS="--image=<img>"` (testcontainers, Podman) |
| PR (all) | Code quality, static analysis, security scans (GHAs) + Konflux PR builds for changed images | automatic; `/retest`, `/test` for re-runs (see [docs/konflux.md](konflux.md#how-pr-comment-commands-match-pipelines)) |
| PR (notebook smoke) | Example notebook against a deployed workbench | `make test-<notebook>` (papermill; needs a deployed workbench, see README) |
| ODH nightly | ods-ci smokes + ITS `its-trigger-nightly` | Jenkins (automatic/scheduled) |
| RHOAI nightly | tier1/2/3 sanity + smoke, product E2E (ods-ci `0500__ide`, opendatahub-tests) | Jenkins against `rhoai-fbc-fragment:rhoai-X.Y-nightly` |

## Release process

### RHOAI releases (DevOps-driven)

The RHOAI train lifecycle (onboarding, nightlies, code freeze, RC, GA) is operated by DevOps.
Our responsibilities:

1. **Train onboarding** — when DevOps cuts a new train, confirm our branch is ready and, if the
   kickoff lands on our side, use the **Release Kickoff Action** GHA (or `make kickoff-release`)
   to bump `versions_config.yml` for the train.
2. **Keep the train green** — nightlies and RCs gate on our builds; failures must be triaged
   within the release channel SLA (see [troubleshooting](bodies-of-water-troubleshooting.md)).
3. **Freeze discipline** — when a train freezes, stop non-critical merges to it; remember the
   train-divergence rule (auto-merge moves to the newest train).

### ODH releases (team-driven)

Recurring task, cloned per cycle (template: [RHAIENG-6297](https://redhat.atlassian.net/browse/RHAIENG-6297);
current: [RHAIENG-7156](https://redhat.atlassian.net/browse/RHAIENG-7156)). The six steps:

1. **Verify ODH code freeze status** — check the ODH release tracker issue and the ODH Release
   Google Calendar.
2. **Validate image tags** — `.tekton/*.yaml` and `manifests/odh/base/params-latest.env` must
   carry the new release tag. Tags must **not** include a patch version; format
   `<train>-v<NN>` (e.g. `3.5-v1.47`), where `<NN>` matches the git release tag.
3. **Publish the release** — run the **"Create release"** GHA (`.github/workflows/create-release.yaml`)
   with the *same tag used for the image builds* (e.g. tag `v1.48.0`, name `3.6-v1.48.0`,
   target branch per the release). It creates the git tag + GitHub release.
4. **Update the release tracker issue** — comment the newly published release on
   [opendatahub-io/workbenches-operator#107](https://github.com/opendatahub-io/workbenches-operator/issues/107).
   ⚠️ This tracker **moved** from `opendatahub-community#202`, which now only takes operator
   release values — do not comment notebook releases there.
5. **Post-release tag bump** — *after* publishing, run the **"Update Tekton Tags"** GHA
   (`.github/workflows/update-tags.yaml`) to prep the *next* release (e.g.
   `3.5-v1.47` → `3.6_ea1-v1.48`). It rewrites the tag in `.tekton/*.yaml` +
   `manifests/odh/base/params-latest.env` and opens a PR — merge it promptly.
6. **Clone the release ticket** for the next cycle, bumping all tag values.

## What to do when (team quick reference)

This table is the core of the in-team training; walk it in onboarding.

| Situation | Do | Notes |
|---|---|---|
| New feature / normal fix | PR to `main`; land when all PR gates are green | Never commit directly to `stable` or RHDS branches |
| Change must reach ODH nightly | Land on `main`, then fast-forward to `stable` via the GHA (`dry_run` first) | Only when `stable` is an ancestor of `main` |
| Change must reach the *newest* RHOAI train | It flows automatically after `stable` | Verify via RHOAI nightly build + Jenkins |
| Change must reach an *older* (frozen) train | Cherry-pick downward by hand (procedure above) | DevOps will not do it; PR needs review before freeze |
| ODH release cycle | Six steps above; clone the release ticket | Tracker: workbenches-operator#107 |
| CVE on a release branch | [docs/cves/](cves/) workflows + the fix-cve agent flow | Per-branch constraint + lockfile verification |
| New image or base image | New directory under `jupyter|codeserver|runtimes`, then Konflux component onboarding | Ask-first item per AGENTS.md; onboarding flow in [docs/konflux.md](konflux.md) |
| Something is broken in the flow | [Troubleshooting guide](bodies-of-water-troubleshooting.md) | Symptom → cause → fix |

## Training record

- **2025-11-18** — QE/developer walk-through of in-repo tests (Jiri Daněk): repo test targets
  demonstrated and acknowledged; **gap identified:** how to run the downstream IDE test surface
  (ods-ci `0500__ide`) was not covered. Covered by:
  - "Testing at each stage" above, and
  - [docs/agents/testing.md](agents/testing.md) (in-repo catalog: targets, markers, CI parity), and
  - per-image "what should work once built" notes being gathered next to the respective
    Dockerfiles (tracked in [RHOAIENG-24093](https://redhat.atlassian.net/browse/RHOAIENG-24093)).
- **Rehearsal:** the next ODH release (RHAIENG-7156) doubles as a live rehearsal of steps 1–6;
  the release ticket is the runbook.

## Knowledge transfer to DevOps

**DevOps owns** (do not edit in our repos; change requests go through them):

- Auto-sync `stable` → RHOAI train: GitHub Actions in
  [`red-hat-data-services/rhods-devops-infra`](https://github.com/red-hat-data-services/rhods-devops-infra)
  (`src/config/main-release-source-map.yaml`, `upstream-source-map.yaml`).
- Konflux pipeline definitions: synced read-only from
  [`opendatahub-io/odh-konflux-central`](https://github.com/opendatahub-io/odh-konflux-central)
  (ODH) and [`red-hat-data-services/konflux-central`](https://github.com/red-hat-data-services/konflux-central)
  (RHOAI) into our `.tekton/` — **never hand-edit `.tekton/`** (see [docs/konflux.md](konflux.md)).
- RHOAI train management, RC promotion, GA release, image mirroring.

**We provide to DevOps** (this is the signoff contract):

| Component | Signoff | Date | Stream | Lake | Ocean | RHDS branch |
|---|---|---|---|---|---|---|
| Notebooks | Jiri Daněk | 2025-08-05 | `main` | `stable` | `rhoai` | `main` |

Keep this row current in the [canonical signoff table](https://docs.google.com/document/d/1LXbAylu-1rCw1gkqNuhLoPC5tzD70gg0jdGy-SBgyYI/edit)
when branch names change.

**How to reach them:** RHOAI DevTestOps office hours (Tuesdays) and
`#rhoai-devtestops-requests` (Slack). Use these for sync failures, train onboarding, and
Konflux trigger issues; see the [troubleshooting guide](bodies-of-water-troubleshooting.md#escalation)
for what to attach.

## References

- Canonical strategy: [Release Strategy – The Bodies Of Water](https://docs.google.com/document/d/1LXbAylu-1rCw1gkqNuhLoPC5tzD70gg0jdGy-SBgyYI/edit)
  (foundational design, not actively maintained; phase status in [RHOAIENG-28641](https://redhat.atlassian.net/browse/RHOAIENG-28641))
- Adoption epic: [RHAIENG-1273](https://redhat.atlassian.net/browse/RHAIENG-1273)
- Mechanisms (verified live): [code-flow-odh-to-rhoai.md](code-flow-odh-to-rhoai.md)
- Builds & triggers: [konflux.md](konflux.md), [ci.md](ci.md), [tide.md](tide.md)
- Tests: [agents/testing.md](agents/testing.md)
- Troubleshooting: [bodies-of-water-troubleshooting.md](bodies-of-water-troubleshooting.md)
- ODH release tracker: [opendatahub-io/workbenches-operator#107](https://github.com/opendatahub-io/workbenches-operator/issues/107)
