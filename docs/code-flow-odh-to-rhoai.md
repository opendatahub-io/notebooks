# Code Flow: opendatahub-io → red-hat-data-services → Nightly & RC Builds

> Investigation of how code flows from the upstream **`opendatahub-io`** GitHub org, into the
> downstream **`red-hat-data-services`** (RHDS/RHOAI) org, and on into **Nightly** and
> **Release Candidate (RC)** builds. Verified via `gh` CLI (repo/workflow/commit inspection),
> `gws` (Google Workspace), and Slack search.

## 0. The model in one line (corroborated by the "Bodies Of Water" doc)

The whole thing is the **Stream → Lake → Ocean** release strategy
([Release Strategy - The Bodies Of Water](https://docs.google.com/document/d/1LXbAylu-1rCw1gkqNuhLoPC5tzD70gg0jdGy-SBgyYI/edit)):

| Body of water | Meaning | Branch | Org / tenant | Built where |
|---|---|---|---|---|
| **Stream** (mainline) | "Your development. Your way." sandbox / trunk | `main` | component-owned | — |
| **Lake** (ODH) | ODH stable, first joint deliverable | `stable` | `opendatahub-io` / `open-data-hub-tenant` | **ODH Nightly** |
| **Ocean** (RHOAI) | RHOAI stable, product-releasable | `rhoai` → synced to RHDS `main` → release branches | `red-hat-data-services` / `rhoai-tenant` | **RHOAI Nightly** + **RC/GA** |

> Note: the doc is the *foundational design* (not actively maintained). Current phase status
> lives in **RHOAIENG-28641**. The mechanisms below are what is actually running today.
> For the *team workflow* (what to do when, release process, troubleshooting), see
> [bodies-of-water.md](bodies-of-water.md) and [bodies-of-water-troubleshooting.md](bodies-of-water-troubleshooting.md).

```text
                     opendatahub-io (UPSTREAM / "Lake")                red-hat-data-services (DOWNSTREAM / "Ocean")
┌──────────────────────────────────────────────────┐        ┌──────────────────────────────────────────────────────┐
│  opendatahub-io/notebooks                          │        │  red-hat-data-services/notebooks                      │
│   • main        (Stream)                           │  sync  │   • main        (Ocean — DevOps-owned)                │
│   • stable      (Lake)  ── ODH build ──────────────┼───────▶│   • rhoai-3.5 / 3.6-ea.2 ... (release branches)       │
│   • 2025a/2024b (ODH release branches)             │        │   • .tekton/* synced from konflux-central             │
└──────────────────────────────────────────────────┘        └──────────────────────────────────────────────────────┘
   Konflux ODH builds (open-data-hub-tenant,                    Konflux RHOAI builds (rhoai-tenant, rhoai-vX)
   app opendatahub-builds) → quay.io/opendatahub/...:odh-stable    → quay.io/rhoai/... + registry.redhat.io/rhoai/...
                                                                      │
                                            ┌─────────────────────────┴──────────────────────────┐
                                            ▼ CI (on-push)                                        ▼ Nightly (on-schedule)
                                       component builds                                  rhoai-fbc-fragment-vX-on-schedule
                                       + auto-nudge chain                                  → quay.io/rhoai/rhoai-fbc-fragment:rhoai-X.Y
                                       (operator→bundle→FBC)                                → Jenkins rhoai-nightly (tier1/2/3, sanity, smoke)
                                            │                                                    │
                                            │                          Stage Promoter (build_type: RC)
                                            │                          LATEST_NIGHTLY FBC → rhtap-releng-tenant
                                            │                          → component/chart release pipelines → production catalog
```

---

## 1. Phase 1 — Upstream development (`opendatahub-io`)

- Development happens in **`opendatahub-io/<repo>`** (e.g. `opendatahub-io/notebooks`, the repo in this checkout).
- PRs merge to `main` via **`openshift-merge-bot[bot]`** (verified in commit history).
- Branches (upstream): `main` (Stream), `stable` (Lake), plus ODH release branches `2025a`, `2024b`, `2024a`, `1.10.x`, ...
- The `stable` branch is the **Lake**: ODH images are built from it.
  - Example `.tekton` PipelineRun (downstream copy, `build.appstudio.openshift.io/repo` → `opendatahub-io/notebooks`):
    - `appstudio.openshift.io/application: opendatahub-builds`
    - `namespace: open-data-hub-tenant`
    - `output-image: quay.io/opendatahub/odh-workbench-...:odh-stable`
    - trigger CEL: `event == "push" && target_branch == "stable" && !(...params-latest.env changed)`
    - `dockerfile: .../Dockerfile.konflux.cpu`, multi-arch (x86_64/arm64/ppc64le/s390x), hermetic, RPM/pip/npm prefetch.
- **ODH Nightly** = builds off `stable`. There is also an ODH nightly CronJob:
  - `rhods-devops-infra/.github/workflows/trigger-odh-nightly.yaml` → `oc create job --from=cronjob/nightly-cronjob -n open-data-hub-tenant`.

## 2. Phase 2 — Upstream → Downstream sync (`opendatahub-io` → `red-hat-data-services`)

Three mechanisms exist; which is used is per-component. (The Bodies doc: *"7/12 = 59% of component teams sync automatically between ODH & RHOAI."*)

1. **Git merge of `upstream/main` into downstream `main`** (the dominant one for notebooks).
   - Downstream `red-hat-data-services/notebooks` has an `upstream` remote → `opendatahub-io/notebooks`.
   - Commit history on downstream `main` shows: `moulalis | Merge remote-tracking branch 'upstream/main'`.
   - i.e. in the downstream repo: `git fetch upstream && git merge upstream/main` → push to downstream `main`.
2. **`Gated-Auto-Merger` (GAM)** — `red-hat-data-services/Gated-Auto-Merger`.
   - Python tool (`src/gam_controller.py`, `hydra_adapter.py`). Reads `config/gam-config.yaml` component defs,
     builds a **Hydra payload**, and **posts a UMB message** to Red Hat **Hydra** CI; gates auto-merge on test result.
   - Records execution metadata (git, index_image, nvr, test_result, auto_merge_url, status) to a `metadata` branch.
   - The `-sync` repos are its targets (e.g. `opendatahub-io/opendatahub-operator` →
     `red-hat-data-services/opendatahub-operator-sync`). See the dashboard exception below.
3. **`sync-upstream-repo` / `sync-git-branches`** — composite GitHub Actions (fork of `dchourasia/sync-upstream-repo`)
   that do a plain git merge from an `UPSTREAM_URL`/branch into a `DOWNSTREAM_URL`/branch using a PAT, typically on a cron.

> **⚠️ Dashboard exception (verified 2026-09-06):** `odh-dashboard` does **not** use GAM for its real sync path.
> - The GAM config's dashboard entry is a defunct test: `opendatahub-io/odh-dashboard` **branch `sync-test`** →
>   `red-hat-data-services/odh-dashboard-sync` **branch `main`** (`ignore_files: [".env",".env.test"]`, `platform: Jenkins`).
>   Consequently **`odh-dashboard-sync` `main` is stale since 2025-01-05** (last commit `96f76adf62`, a GAM
>   `Merge commit '<sha>'`) and the repo has only `main` + `sync-test` — **no `rhoai-X.Y` branches at all**.
> - The **real downstream** is `red-hat-data-services/odh-dashboard` (non-`-sync`), synced by the **dashboard team
>   directly** (commits authored by `m-rafeeq`, `moulalis`, `ubhattarai`): `Merge remote-tracking branch
>   'upstream/main'` into `main` and the `rhoai-X.Y(-ea.N)` release branches. Because it's a plain branch merge,
>   **upstream squash-merge SHAs are preserved verbatim** — verified: `2d6770547c827f86b1f99d466b78aca5a899a6cc`
>   ("chore: initialize fullsend per-repo installation (#9645)") exists in both upstream `main` and downstream
>   `rhoai-3.6-ea.2` with the identical SHA. Downstream-only changes (e.g. `(#2483)` registry digest pins) interleave
>   in the same branch history.
> - Konflux builds the dashboard from **`red-hat-data-services/odh-dashboard@rhoai-3.6-ea.2`**
>   (`Dockerfile.konflux.dashboard-operator`, Component `odh-dashboard-operator-v3-6-ea-2` in `rhoai-tenant`), never
>   from the `-sync` repo.

> Also: `.tekton/` pipeline defs are kept in sync with **konflux-central** by
> **`rhods-devops-app[bot]`** — commit `sync pipelineruns with konflux-central - <sha>`.

## 3. Phase 3 — Downstream `main` → release branches (Ocean)

- Release branches: `rhoai-2.25`, `rhoai-3.3`, `rhoai-3.4`, `rhoai-3.5`, `rhoai-3.6-ea.1`, `rhoai-3.6-ea.2`, ...
  (z-streams cut as `rhoai-X.Y` from a past pointer; changes cherry-picked down — per the Bodies doc FAQ).
- **Auto-merge main → release**: `rhods-devops-infra/.github/workflows/main-release-auto-merge.yaml`
  ("Main to Release - Auto-Merge"), across all RHOAI component repos (incl. `notebooks`, `odh-dashboard`, `rhods-operator`).
- **Release onboarding**: `rhods-devops-infra/.github/workflows/onboard-release-branches.yaml` (cron `0 1 * * *` + manual)
  creates a new release branch + its Konflux applications.
- **Freeze behavior**: when a newer train is onboarded, auto-merge is turned **off** for the older train
  (e.g. 3.6-EA1) to prevent leak-through; older branches become **manual cherry-pick only** (documented in `#wg-3_6_ea1`).
- Within-repo branch sync: `notebooks/.github/workflows/sync-branches-through-pr.yml` (source→target PR).
- `merge-main-to-stable-fast-forward.yaml` fast-forwards `stable` from `main` (RHOAIENG-60781).

## 4. Phase 4 — Konflux builds (RHOAI downstream) + the auto-nudge chain

**Build config layer (where the "truth" lives):**
- **`konflux-central`** — **single source of truth for all PipelineRun definitions** (48+ components).
  README: *"PipelineRun files are authored and maintained here, then automatically synced to component repos."*
  Structure: `pipelineruns/{component}/.tekton/` (e.g. `pipelineruns/notebooks/.tekton/`) + `pipelines/`
  (`container-build.yaml`, `multi-arch-container-build.yaml`, `fbc-fragment-build.yaml`).
  Synced into component repos by `.github/workflows/sync-pipelineruns.yml` (as `rhods-devops-app[bot]`) —
  component `.tekton/` dirs are **read-only downstream**.
  Branch model: `main` = **PR pipelines + tooling only (no push pipelines)**; `rhoai-X.Y` (incl. `-ea.N`) =
  push+PR pipelineruns. Branches are independent (no main→release flow).
- **`red-hat-data-services/RHOAI-Build-Config` (RBC)** — operator/catalog build-config repo (NOT the pipeline source).
  On release branches: `catalog/<ocp>/` FBC catalogs, `bundle/` (operator bundle),
  `config/build-config.yaml` (quay repo mappings for every component image incl. `rhoai/odh-workbench-*`),
  `release/stage/RC<N>/` + `release/prod/` (Konflux **Release CRs**), `schedule/*.txt` trigger files,
  `builds/force-trigger-rhoai-*.txt` (manual re-trigger markers), `.tekton/` (operator-bundle + fbc-fragment +
  helm-chart push/scheduled pipelineruns) + `.github/workflows` (below).
- **`rhoai-konflux-tasks`** — custom Tekton **task** library, consumed by git-resolver from konflux-central pipelines
  (`rhoai-init`, `trigger-bundle-build`, `trigger-operator-build`, `generate-snapshot-for-group-testing`,
  `container-image-mirror`, ...).
- **`RHOAI-Konflux-Automation`** — Python processor tooling, checked out as `utils/` by RBC / rhods-operator workflows:
  `fbc-processor.py`, `processors/{bundle-processor,operator-processor}.py`, `release-helper/`, `stage-promoter/`.
- **Not this path:** `aipcc-konflux-data` (AIPCC / RHEL-AI / RHAIIS base images — different product);
  `pull-request-pipelines` (empty repo); `RHOAI-Build-Config-rm` (6 MB test/POC sandbox for P-a-C / SA-migration /
  scheduled-pipeline experiments — **not** a "remove" variant).

**Konflux application / component naming (tenant `rhoai-tenant`):**
- Per release, a Konflux **Application** `rhoai-vX-Y` (label `appstudio.openshift.io/application: rhoai-vX-Y`);
  a **`rhoai-fbc-vX-Y`** app carries the FBC. PR pipelines use app `automation`.
- Per-image **Components**, e.g. `odh-workbench-jupyter-minimal-cpu-py312-v3-5`, `odh-operator-v3-5`,
  `odh-operator-bundle-v3-5`, `rhoai-fbc-fragment-v3-5` (notebooks: 18 `*-push.yaml` components on `rhoai-3.5`).
- Components build from **release branches** (not `main`).
- **Konflux onboarding** (new component): `/create-component-onboarding-jira` → generate component YAML + schema
  validation + Dockerfile digest check → registers `RELATED_IMAGE_*` in **ODH-Build-Config** (upstream) and
  **RHOAI-Build-Config** (downstream).

**How Konflux subscribes to GitHub (Pipelines-as-Code):**
- Watches each component repo's **`.tekton/`** dir (synced read-only from konflux-central). Triggers are
  per-PipelineRun annotations:
  - push/scheduled → `pipelinesascode.tekton.dev/on-cel-expression` = `event=="push" && target_branch=="rhoai-X.Y"
    && "<path>".pathChanged()`, with `build.appstudio.openshift.io/repo: …/red-hat-data-services/<repo>?rev={{revision}}`.
  - PR → `on-event: [pull_request]` + `on-target-branch` + `on-comment: "^/build-konflux|…"` + `on-label`.
- **Pipeline refs are git-resolved** from konflux-central: `resolver: git, url: …/konflux-central.git,
  revision: '{{ target_branch }}', pathInRepo: pipelines/multi-arch-container-build.yaml` — each release branch
  resolves pipelines from its **own** konflux-central branch.
- **Manual re-trigger:** `konflux-central/retrigger-builds.yml` (touches a `*-push.yaml` timestamp → sync → push →
  pathChanged fires) and RBC `builds/force-trigger-*.txt` markers.

**The auto-nudge chain** (from Slack `#rhoai-devtestops-requests`, RHAIENG-3124) — how one workbench build
cascades into a new catalog:

```text
Workbench code change (red-hat-data-services/notebooks release branch)
  → Konflux Component Build (push pipeline, .tekton/*-push.yaml;
       build-nudges-ref + build-nudge-files: build/operator-nudging.yaml)
  → Nudge PR → rhods-operator repo  (auto-merged by InstaMerge)
  → operator-processor.py (RHOAI-Konflux-Automation)
       queries Quay for digests + vcs-ref labels → updates operands-map.yaml, manifest-config.yaml,
       additional-images-patch.yaml
  → Operator Build → Nudge → Bundle repo
  → bundle-processor → injects RELATED_IMAGE_* into CSV
  → Bundle Build → Nudge → RHOAI-Build-Config repo
  → FBC-processor → renders catalog.yaml, applies patches
  → final catalog.yaml pushed to release branch (e.g. rhoai-3.5)
  → FBC Fragment Build → available in registry
```

**Image destinations & tag naming:**
- **`quay.io/rhoai/…`** (dev / nightly / RC source; roles `rhoai-consumer`/`rhoai-dev`/`rhoai-qe`/`rhoai-devops`
  via `app-interface`):
  - workbench/runtime: `quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9:{{target_branch}}` (e.g. `:rhoai-3.5`)
    + extra tag `{{target_branch}}-{{revision}}` (SHA-suffixed).
  - operator: `quay.io/rhoai/odh-rhel9-operator:{{target_branch}}`; bundle: `quay.io/rhoai/odh-operator-bundle:{{target_branch}}`;
    FBC fragment: `quay.io/rhoai/rhoai-fbc-fragment:{{target_branch}}`.
  - **Nightly** = same repos **plus** `{{target_branch}}-nightly` (only scheduled pipelineruns add it,
    e.g. `rhoai-fbc-fragment:rhoai-3.5-nightly`).
  - PR: `quay.io/rhoai/pull-request-pipelines:notebooks-{{revision}}`, `image-expires-after: 5d`.
  - Base images pinned by digest from `quay.io/aipcc/base-images/*` (e.g. `jupyter/…/build-args/konflux.cpu.conf`:
    `BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-…@sha256:…`, `PRODUCT=rhoai`, `RELEASE=3.5`).
- **`registry.redhat.io/…`** (prod): `release_processor.py` uses `PRODUCTION_REGISTRY='registry.redhat.io'`,
  `DEV_REGISTRY='quay.io'` — stage/prod promotion moves images quay→registry.redhat.io.
  `RHOAI-Build-Config/.tekton/images-mirror-set.yaml` = `ImageDigestMirrorSet` CR mirroring
  `registry.redhat.io/rhoai` → `quay.io/rhoai` / `quay.io/rhoai-private` (disconnected/proxy pulls).
- **Quay image-tag style is branch / SHA / `-nightly` / `ocp-4.NN-rhoai-X.Y` — NOT date-stamped.** Verified live
  2026-09-11 (`skopeo list-tags`, 248k tags): `rhoai-3.6-ea.2`, `rhoai-3.6-ea.2-<sha>`, `rhoai-3.6-ea.2-nightly`,
  `ocp-4.19-rhoai-3.5-ea.2`, `ocp-4.19-rhoai-3.6-ea.1-<sha>`, per-arch `<…>-linux-{x86-64,arm64,ppc64le,s390x}`,
  aux `<…>.git`/`<…>.fips-buckets`. OCP prefix has a **dot** (`ocp-4.19`…`ocp-4.22`, `ocp-5.*`); there are **no
  `ocp-*-nightly` tags** (per-OCP "nightly" = the per-OCP branch floating tag). (Konflux *CR* names use the dotless
  `ocp-4NN`, e.g. app `rhoai-fbc-fragment-ocp-421` — don't confuse the two.) The `IMAGE_TAG=$(RELEASE)_$(DATE)`
  in the notebooks Makefile is a *local/dev* convention only; date strings appear in prod only inside trigger files
  (`echo $(date) > schedule/*.txt`).
- Test images: `quay.io/opendatahub/workbench-images-tests` (Playwright E2E), `quay.io/redhat-appstudio-qe` (Konflux E2E).

## 5. Phase 5 — NIGHTLY builds (verified trigger chain)

The nightly is a **scheduled** cascade that ends in `-nightly`-tagged images + an FBC fragment. Verified chain:

```text
rhods-devops-infra/.github/workflows/trigger-nightlies.yaml   on: schedule cron '0 0 * * *'
  └ reads src/config/releases.yaml → benc-uk/workflow-dispatch → per release branch:
rhods-operator/.github/workflows/trigger-nightly-operator-build.yaml
  └ operator-processor.py: prefetches latest operand manifests/charts at branch tip,
    writes build/schedule/operator-tekton-trigger.txt → commit + push
rhods-operator/.tekton/odh-operator-v3-5-scheduled.yaml       CEL: push && target_branch=="rhoai-3.5"
  && "build/schedule/operator-tekton-trigger.txt".pathChanged()   → scheduled operator build
RBC .github/workflows/trigger-nightly-fbc-build.yaml          on: push paths [schedule/catalog-github-trigger.txt]
  └ fbc-processor.py -op extract-snapshot-images (reads latest images from the Konflux SNAPSHOT)
    → patches catalog/<ocp>/rhods-operator/catalog.yaml → writes schedule/catalog-tekton-trigger.txt → push
RBC .tekton/rhoai-fbc-fragment-v3-5-scheduled.yaml            CEL on catalog-tekton-trigger.txt; build-type: nightly
  → quay.io/rhoai/rhoai-fbc-fragment:rhoai-3.5  +  rhoai-3.5-nightly
RBC .github/workflows/trigger-nightly-bundle-build.yaml       on: push [schedule/bundle-github-trigger.txt]
  └ bundle-processor.py → schedule/bundle-tekton-trigger.txt → .tekton/odh-operator-bundle-v3-5-scheduled.yaml
fbc-insta-merge.yaml / bundle-insta-merge.yaml               auto-merge the trigger-file PRs (konflux-internal-p02[bot])
```

- **Artifact:** `quay.io/rhoai/rhoai-fbc-fragment:rhoai-X.Y` + `:rhoai-X.Y-nightly`.
  - Live example (from `#rhoai-build-notifications`, posted by `rhoai-devops-bot`):
    `:nightly: A new Nightly Build is available for RHOAI v3.6.0-ea.2` →
    image `quay.io/rhoai/rhoai-fbc-fragment:rhoai-3.6-ea.2@sha256:589c3b8d...`, commit in `RHOAI-Build-Config`,
    build `.../ns/rhoai-tenant/pipelinerun/rhoai-fbc-fragment-v3-6-ea-2-on-schedule-2zp8d`.
- **Nightly tests:** Jenkins (`jenkins-csb-rhods-opendatascience.dno.corp.redhat.com`) —
  `rhoai/rhoai-nightly/.../rhoai-tier1|tier2|tier3`, `rhoai-sanity`, `rhoai/autotrigger-smoke` (RHODS Nightly Smoke Tests),
  deployed on BVT GCP clusters (`bvt-rhoai-gcp-1/2`, `selfmanaged-GCP-OCP-4.21.x`); results in ReportPortal,
  failures/summary posted to `#rhoai-build-notifications`. Upstream ODH smoke: `odh/autotrigger-smoke` (`odh-odh-stable`).
- **Gate:** "If all RHOAI component builds are green, nightlies are available." A failing component build blocks
  that version's nightlies.
- **CI vs Nightly:** CI = `*-push.yaml` (`build-type: ci`, CEL on real content paths, e.g. `catalog/**.pathChanged()`);
  Nightly = `*-scheduled.yaml` (`build-type: nightly`, CEL on `schedule/*-trigger.txt`, adds the `-nightly` tag).
  FBC `build-type` enum = `["ci","nightly","stage"]`.

## 6. Phase 6 — RELEASE CANDIDATE (RC) builds

- **RC = an EA (early-access) release, version `X.Y.Z-ea.N`** (currently `3.6.0-ea.2`). Release stages
  (RHOAI): `Pre-RC → Stage → Perform-RC → Production → Perform-GA → Post-GA`.
- **An RC is a Konflux `Release` CR pinning a `Snapshot`** — not a re-build of components. Stored under
  `RHOAI-Build-Config/<branch>/release/stage/RC<N>/` (e.g. `rhoai-3.5/release/stage/RC4/stage-release-<sha>/`):
  - `release-components/…yaml` = `kind: Release, spec: {releasePlan: rhoai-onprem-vX-Y-components-stage,
    snapshot: rhoai-vX-Y-<epoch>}`.
  - `release-fbc/…yaml` = per-OCP `Release` (`releasePlan: rhoai-onprem-vX-Y-ocp-4NN-fbc-stage,
    snapshot: rhoai-fbc-fragment-ocp-4NN-<epoch>`); plus `snapshot-components/`, `snapshot-fbc/`, `release-fbc-addon/`.
  - Prod analogues: `release/prod/prod-release-<epoch>/` (`templates/prod/release-{components,fbc}-prod.yaml`).
- **What selects the RC images:** `RHOAI-Konflux-Automation/utils/release-helper/generate-stage-release-artifacts.sh`
  picks the FBC fragment by **per-OCP branch tag** `quay.io/rhoai/rhoai-fbc-fragment:ocp-4.NN-rhoai-X.Y[-ea.N]`
  (stage; verified live: `ocp-4.19-rhoai-3.5-ea.2`) — the `LATEST_NIGHTLY` default resolves to the non-ocp
  `quay.io/rhoai/rhoai-fbc-fragment:<branch>-nightly` (verified live: `rhoai-3.6-ea.2-nightly`) — `skopeo inspect`s
  the digest + labels, and fills the Snapshot/Release templates. Applied by `release-to-stage.sh`:
  `oc apply -f snapshot-*` then `oc apply -f release-*`.
- **Sync gate (the "gated" part):** `release-fbc-to-stage.sh` **fails if any per-OCP fragment's
  `rbc-release-branch.commit` image label ≠ the nightly's** — i.e. the operator/bundle/component fragments must all
  trace to the same release-branch commit before promotion. Labels come from `catalog_build_args.map` (which pins the
  git commit of every downstream component, incl. `ODH_WORKBENCH_JUPYTER_*_GIT_COMMIT` from `red-hat-data-services/notebooks`).
- **Runs in a different Konflux tenant:** **`rhtap-releng-tenant`** (release engineering / RHTAP), app `rhoai-vX`,
  via **component release pipeline** + **chart release pipeline** (`managed-*` PipelineRuns). The promoter waits for
  green PipelineRuns in `rhtap-releng-tenant` (Konflux / Enterprise-Contract release gates) + Conforma.
  `push-to-stage.yaml` uses `GITHUB_RKA_ORG: rhoai-rhtap`.
- **Stage Promoter workflows** are the entry points: `rhods-devops-infra/.github/workflows/stage-promoter.yaml`
  (inputs `release_branch`, `rhoai_version`, `fbc_image_uri=LATEST_NIGHTLY`, `build_type: Nightly|RC`,
  `release_scope: all|components|charts|fbc`, `validate_conforma_and_smokes`, `validate_modular_operators_manifests`,
  `force_push/force_release`; version gates: charts ≥ 3.4, modular operators ≥ 3.5) and the siblings
  `RHOAI-Build-Config/.github/workflows/push-to-stage.yaml` / `multi-push-to-stage.yaml`.
- **Core promotion code:** `RHOAI-Konflux-Automation/utils/stage-promoter/stage_promoter.py`
  (`PRODUCTION_REGISTRY='registry.redhat.io'`, `PACKAGE_NAME='rhods-operator'`, `RESET_CHANNELS={'beta'}` — the **beta**
  OLM channel is **reset** for a release, others merge with the base catalog; `EA_VERSION_PATTERN = X.Y.Z-ea.N[.H]`).
  ⚠️ The **`red-hat-data-services/gated-artifacts-promoter` repo is an EMPTY placeholder** (1 commit, size 0) — the real
  machinery is in `RHOAI-Konflux-Automation`.
- **Consumption:** the RC bundle lands in the OLM catalog and is promoted into the **`beta` channel** (the reset
  channel); the gitops chart (`operator.rhoai.olm.channel: beta`, `source: redhat-operators`) picks it up.
- **Failure signal** (from `#rhoai-build-notifications`): "RC stage push failed during component release phase /
  due to the component release pipeline exited with status … after 3 retry attempts" — with logs in
  `red-hat-data-services/rhods-devops-infra/actions/runs/...` and Konflux `.../ns/rhtap-releng-tenant/...`.

## 6b. GitOps + how a build is actually consumed in a cluster

- **`odh-gitops`** (both `opendatahub-io/` and `red-hat-data-services/`) is **not** an ArgoCD app-of-apps and has
  **no per-env folders** — it's **layered Kustomize + Helm**. Root `kustomization.yaml` = `dependencies/` +
  `configurations/` (prerequisite operators: cert-manager, kueue, LWS, JobSet, NFD, NVIDIA, Kuadrant, ...).
  Operators deploy via **Helm charts**: `charts/rhai-on-openshift-chart` (OLM Subscription + `DataScienceCluster` CR;
  `olm: {source: redhat-operators, sourceNamespace: openshift-marketplace}`, `operator.rhoai.olm: {channel: beta,
  name: rhods-operator}`); ODH uses `channel: fast-3`, `source: community-operators`; `charts/rhai-on-xks-chart` (multi-cloud).
- **Channel/environment layout = branches, not folders.** Downstream gitops: `rhoai-3.4`, `rhoai-3.5`,
  `rhoai-3.6`, `rhoai-3.6-ea.1/ea.2`, ... — **a branch per version, a z-stream TAG per release** (e.g. `rhoai-3.0.0`).
  Branch created from `main` at code freeze; diverges by cherry-picks. `Makefile` `RHOAI_VERSION ?= 3.5.0` +
  `scripts/update-rhoai-version.sh` (pulls `patch.version` from `opendatahub-io/ODH-Build-Config/main/bundle/bundle-patch.yaml`).
- **No ImageStreams / no `params-latest.env` / no quay refs in gitops** (code search: 0 hits). The consumption path is
  **OLM catalog → bundle `relatedImages`**: the FBC catalog
  `RHOAI-Build-Config/catalog/rhoai-3.5/v4.21/rhods-operator/catalog.yaml` (~42k lines; `olm.package`/`olm.channel`/
  `olm.bundle`) pins workbench images digest-only, e.g. `image: registry.redhat.io/rhoai/odh-workbench-jupyter-minimal-cpu-
  py312-rhel9@sha256:a16f8449...`; bundle `registry.redhat.io/rhods/odh-operator-bundle@sha256:...`.
- **Chart round-trip:** downstream gitops `.github/workflows/helm-sync.yml` — on push to `rhoai-[23].[0-9]*` branches,
  rsyncs `charts/{rhai-on-openshift-chart,rhai-on-xks-chart,dependencies}` → `RHOAI-Build-Config/to-be-processed/helm/<chart>/`
  on the same-named branch (author "Openshift-AI DevOps").

## 7. Notebooks-specific image wiring (how a build becomes a manifest)

This is the part unique to the `notebooks` component:

- **`manifests/base/params.env` + `commit.env`** = **pinned release** images (digest-pinned `@sha256:`;
  `registry.redhat.io/rhoai/...` for RHOAI, `quay.io/modh/...` for ODH).
- **`manifests/base/params-latest.env` + `commit-latest.env`** = **latest/nightly** (floating) images + source commit SHAs.
- **`notebooks-digest-updater.yaml`** → **`ci/sha-digest-updater.sh`** (runs in both orgs):
  - Fetches the latest commit hash of the branch (or `user_hash`).
  - For each image, `skopeo inspect` the registry and select the tag matching
    `^<name>-YYYYMMDD-<hash>$` (upstream/ODH, e.g. `jupyter-minimal-ubi9-python-3.11-20250310-60b6ecc`)
    or the downstream regexes (`^v3-YYYYMMDD-<hash>$`, `^cuda-*-3.11-YYYYMMDD-<hash>$`, `^rocm-*-pytorch-*-3.11-YYYYMMDD-<hash>$`).
  - Pins the matching digest into `params-latest.env` and the SHA into `commit-latest.env`, via an automated PR.
  - ⚠️ **Scope note:** this `params*.env` mechanism matches **date-stamped ODH tags** and is the ODH-side wiring. For
    **RHOAI**, the *primary* consumption path is the **OLM FBC catalog** (see §6b — digest-pinned, built by
    `fbc-processor` from the Konflux snapshot), not `params.env`. The downstream date-stamped regexes in this script
    do **not** match the current Konflux output tags (`:rhoai-X.Y` / `:rhoai-X.Y-nightly`), so this is effectively
    ODH-oriented / partly legacy downstream (consistent with the "skipped-images" logs and RHAIENG-3124).
- **`check-image-availability.yaml`** — verifies every image in `params*.env` exists in its registry;
  alerts (issue + Slack) when a Konflux build failed or a tag vanished (e.g. `#2330`/`#3445`).
- **`update-commit-latest-env.yaml`** — separate nightly GHA that extracts `vcs-ref` labels for `commit-latest.env`
  (currently broken post-`registry.redhat.io` migration — **RHAIENG-3124**; fix path = use the Pyxis Catalog API
  as in `manifests/tools/generate_envs.py`).
- **`versions_config.yml`** (downstream-only) = "primary release command" file:
  `release.full_version` (e.g. `3.6.0`), `rhds_os_base` (`el9.8`), `python_version` (`3.12`),
  and `artifacts.base_image.*` (rhds `channel: fast|stable`, odh `origin: in-house`, CUDA/ROCm `acc_version`).
  - **New release stream** (e.g. 3.5→3.6): update `full_version` + preferred image versions → **`make kickoff-release`**.
  - **Mid-release image bumps**: update preferred versions → `make sync-build-args-from-versions` → `make refresh-lock-files`.
- **`release-kickoff.yaml`** — manual GHA: applies optional `versions_config.yml` overrides, runs `make kickoff-release`,
  validates with `make test`, opens a PR. Uses git-crypt secrets + scoped Quay creds (`quay.io/aipcc`, `quay.io/rhoai`).
- **Makefile** (downstream): `RELEASE ?= 3.6`, `PRODUCT=odh|rhoai` selects `build-args/` conf, builds
  `Dockerfile.konflux.cpu/cuda/rocm`. (`IMAGE_TAG ?= $(RELEASE)_$(DATE)` is a **local/dev** tag convention only —
  production Konflux tags are `:rhoai-X.Y` / `:rhoai-X.Y-nightly`, see §4/§5.)

## 8. Key repos & automations (quick reference)

| Concern | Repo / workflow |
|---|---|
| Upstream source of truth | `opendatahub-io/<component>` (`main`/`stable`/release branches) |
| Downstream mirror | `red-hat-data-services/<component>` (forks) |
| Upstream→downstream sync | `Gated-Auto-Merger` (Hydra/UMB), `sync-upstream-repo`, `sync-git-branches`, `upstream/main` merge |
| Dashboard sync (exception) | direct team sync into `red-hat-data-services/odh-dashboard` (upstream squash SHAs preserved); GAM/`odh-dashboard-sync` defunct since 2025-01 |
| **`.tekton/` PipelineRun source of truth** | `konflux-central` (`pipelineruns/` + `pipelines/`; synced by `sync-pipelineruns.yml` / `rhods-devops-app[bot]`) |
| Central RHOAI build config | `RHOAI-Build-Config` (`catalog/`, `bundle/`, `builds/`, `config/`, `release/stage/RC<N>/`, `release/prod/`, `.tekton/`) |
| Build processors (Python) | `RHOAI-Konflux-Automation` (`fbc-processor`, `operator/bundle-processor`, `release-helper/`, `stage-promoter/`) |
| Tekton task library | `rhoai-konflux-tasks` (`rhoai-init`, `trigger-*-build`, `container-image-mirror`, …) |
| main→release auto-merge | `rhods-devops-infra/main-release-auto-merge.yaml` |
| Release onboarding | `rhods-devops-infra/onboard-release-branches.yaml` |
| **Nightly cascade** | `rhods-devops-infra/trigger-nightlies.yaml` (cron) → `rhods-operator/trigger-nightly-operator-build.yaml` → `RHOAI-Build-Config/trigger-nightly-fbc-build.yaml` + `trigger-nightly-bundle-build.yaml` → `*-scheduled.yaml` (`build-type: nightly`, `-nightly` tag) |
| **RC = Konflux Release CRs** | `RHOAI-Build-Config/<branch>/release/stage/RC<N>/` (`release-components`, `release-fbc`, snapshots); prod under `release/prod/` |
| **RC / Stage promotion** | entry: `rhods-devops-infra/stage-promoter.yaml`, `RHOAI-Build-Config/push-to-stage.yaml`; code: `RHOAI-Konflux-Automation` `stage_promoter.py` + `release-helper/release-fbc-to-stage.sh` (rhtap-releng-tenant) |
| Promotion gating | `rbc-release-branch.commit` label sync-check + Conforma + green in `rhtap-releng-tenant` (`gated-artifacts-promoter` repo is empty) |
| Instamerger (nudge/trigger PRs) | `instant-merger` / `insta-merge.yaml`, `fbc-insta-merge.yaml`, `bundle-insta-merge.yaml` |
| ODH nightly (upstream) | `rhods-devops-infra/trigger-odh-nightly.yaml` (`nightly-cronjob`, `open-data-hub-tenant`) |
| Notebooks image wiring | `notebooks/.github/workflows/notebooks-digest-updater.yaml`, `check-image-availability.yaml`, `update-commit-latest-env.yaml`, `release-kickoff.yaml`, `ci/sha-digest-updater.sh`, `versions_config.yml` |
| Upstream build config | `opendatahub-io/ODH-Build-Config` (`bundle/bundle-patch.yaml`), `opendatahub-io/odh-build-metadata`, `opendatahub-io/odh-konflux-central` |
| **Consumption (gitops)** | `odh-gitops` (Kustomize+Helm; branch-per-version, z-stream tags) → `charts/rhai-on-openshift-chart` → OLM catalog `relatedImages`; `helm-sync.yml` round-trips charts into RBC |

## 9. Primary sources (evidence)

- `gh` — repo lists for both orgs; workflows in `opendatahub-io/notebooks` (local) and `red-hat-data-services/notebooks`;
  `Gated-Auto-Merger` (`config/gam-config.yaml`, `src/*`); `rhods-devops-infra` workflows; `RHOAI-Build-Config`
  (`catalog/`, `builds/`, `release/stage/RC<N>/`, `trigger-nightly-fbc-build.yaml`, `push-to-stage.yaml`);
  `konflux-central` (`pipelineruns/notebooks/.tekton/`, `pipelines/fbc-fragment-build.yaml`); downstream `.tekton/`
  PipelineRun; downstream `versions_config.yml` + Makefile; commit history (authors) on both `main`s.
- Slack — `#rhoai-build-notifications` (nightly/RC messages, `rhoai-devops-bot`), `#rhoai-devtestops-requests`
  (Konflux nudge chain, RHAIENG-3124, Quay orgs), `#team-notebooks` (EA1/EA2 auto-merge cut, PR #2807),
  `#wg-3_5/3_6_ea1` (code freeze, onboarding), `#konflux-users`.
- Gmail — Jenkins nightly autotrigger mails (`ods-qe-jenkins@redhat.com`: `devops/nightly-autotrigger`,
  `odh/autotrigger-smoke`), image-availability alert mails.
- Google Doc — "Release Strategy - The Bodies Of Water" (full text, all sections).

## 10. Subagent cross-check (corrections incorporated)

Two background subagents independently verified the build-config and gitops/promotion internals and **corrected**
several earlier assumptions in this report:
1. **`konflux-central` is the single source of truth** for `.tekton/` PipelineRuns (component `.tekton/` is read-only,
   synced via `sync-pipelineruns.yml`); `RHOAI-Build-Config` is the operator/catalog config, not the pipeline source.
2. **Konflux production image tags are `:rhoai-X.Y` / `:rhoai-X.Y-nightly` / `:ocp-4.NN-rhoai-X.Y` — not date-stamped**
   (verified live 2026-09-11 via `skopeo list-tags`, 248k tags; no `ocp-*-nightly` tags; Konflux *CR* names use
   dotless `ocp-4NN`).
   `IMAGE_TAG=$(RELEASE)_$(DATE)` is local/dev only; date strings live only in `schedule/*.txt` trigger files.
   (So the notebooks `sha-digest-updater.sh` downstream date-regexes are ODH-oriented / partly legacy.)
3. **RC = a Konflux `Release` CR pinning a `Snapshot`** (stored `RHOAI-Build-Config/<branch>/release/stage/RC<N>/`),
   over an **EA (`X.Y.Z-ea.N`) branch** — not a re-build; promoted via `rhtap-releng-tenant` and consumed through the
   OLM **`beta`** (reset) channel.
4. **`gated-artifacts-promoter` is an empty placeholder**; the real promotion code is in
   `RHOAI-Konflux-Automation` (`stage_promoter.py` + `release-helper/`), gated by the `rbc-release-branch.commit`
   label sync-check + Conforma + green in `rhtap-releng-tenant`.
5. **gitops = Kustomize+Helm (not ArgoCD app-of-apps); no ImageStreams** — consumption is via the OLM catalog
   `relatedImages`; channel layout is **branch-per-version + z-stream tags**; charts round-trip into RBC via `helm-sync.yml`.
6. **Repo disambiguation:** `aipcc-konflux-data` = different product; `pull-request-pipelines` = empty;
   `RHOAI-Build-Config-rm` = POC sandbox.
7. **Dashboard sync path (correction, verified 2026-09-06):** `odh-dashboard-sync` `main` is stale since 2025-01 and
   the repo has no release branches — the real path is direct branch sync by the dashboard team into
   `red-hat-data-services/odh-dashboard` (upstream squash SHAs preserved verbatim; Konflux builds from
   `odh-dashboard@rhoai-X.Y(-ea.N)`). See the §2 callout.

**Still not fully verified** (would need more digging): who writes the `schedule/*-github-trigger.txt` PRs
(`konflux-internal-p02[bot]` source); how an RC version is stamped into the CSV; the `pcc/` (Data Science Pipelines)
catalog path. (In-cluster Application/Snapshot/Release/ReleasePlan CRs are now verified — §11.)

## 11. In-cluster verification (read-only `oc`, 2026-09-06)

Logged into both Konflux clusters (`oc login --web`) and confirmed the CR objects directly.

**Cluster A — `stone-prod-p02`** (`api.stone-prod-p02.hjvn.p1.openshiftapps.com`), tenants incl. `rhoai-tenant`,
`rhtap-releng-tenant`, `ai-tenant`:
- **Applications** (`appstudio.redhat.com`): `rhoai-v3-5` (76d), `rhoai-v3-6-ea-1` (40d), `rhoai-v3-6-ea-2` (18d),
  plus per-OCP `rhoai-fbc-fragment-ocp-412…422` and POC apps — confirms one Application per release stream + one per
  supported OCP for the FBC fragment.
- **Components**: 119 per release (e.g. `odh-workbench-jupyter-minimal-cpu/cuda/rocm-py312-v3-6-ea-2`,
  `odh-workbench-jupyter-pytorch-cuda-py312-v3-6-ea-2`, `odh-pipeline-runtime-*-v3-6-ea-2`, `odh-operator-v3-6-ea-2`,
  `odh-operator-bundle-v3-6-ea-2`) — the notebooks images are Konflux components named `…-vX-Y`.
- **Releases** (RC/stage + prod), all in `rhoai-tenant` — a **group of Release CRs** per Stage cut, e.g. for v3-6-ea-1:
  - `rhoai-v3-6-ea-1-stage-1788377180` → `releasePlan: rhoai-onprem-v3-6-ea-1-components-stage`, `snapshot: rhoai-v3-6-ea-1-1788377180`
  - `rhoai-v3-6-ea-1-charts-stage-1788382219` → `rhoai-onprem-v3-6-ea-1-charts-stage`
  - `rhoai-fbc-fragment-ocp-4{19,20,21,22}-stage-1788411101` → `rhoai-onprem-v3-6-ea-1-ocp-4NN-fbc-stage` (one per OCP)
  - `rhoai-fbc-addon-ocp-419-stage-1788411101` → `rhoai-addon-v3-6-ea-1-ocp-419-fbc-stage`
  - prod: `rhoai-fbc-fragment-ocp-416-prod-1786412790` → `rhoai-onprem-v2-25-ocp-416-fbc-prod` (**Succeeded**)
  - this is exactly the `release_scope: all|components|charts|fbc` (+addon) fan-out.
- **ReleasePlans**: one per (version, scope, env) — `rhoai-onprem-vX-Y-{components,charts,ocp-4NN-fbc}-{stage,prod}` +
  `rhoai-addon-vX-Y-ocp-4NN-fbc-stage` — each with `application: <app>` and **`target: rhtap-releng-tenant`** (the
  release pipeline runs there). The stage/prod distinction is in the **name suffix**, not the `environment` field.
- **Snapshots** pin every component image by **`@sha256:` digest**, e.g.
  `quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9@sha256:dbdaf…`,
  `…-jupyter-minimal-cuda/rocm-py312-rhel9@sha256:…`, `…-jupyter-pytorch-cuda-py312-rhel9@sha256:…`,
  `quay.io/rhoai/odh-rhel9-operator@sha256:7318…`, `quay.io/rhoai/odh-operator-bundle@sha256:36c6…` — the digest
  pinning that flows into the OLM catalog.
- **Conforma gates**: `conforma-registry/chart/fbc-rhoai-prod-v{3-4,3-5,3-6-ea-1}` PipelineRuns in `rhoai-tenant` —
  the Conforma validation runs that gate prod release (currently `PipelineRunPending`).
- **Release pipelines** run in the **shared** `rhtap-releng-tenant` as `managed-*` PipelineRuns
  (`appstudio.openshift.io/service: release`, `pipelines.appstudio.openshift.io/type: managed`) using the
  `konflux-ci/release-service-catalog` pipeline; multi-product (e.g. `kmod-nvidia-jetson`, RHOAI). 5 started 2026-09-06.

**Cluster B — `stone-prd-rh01`** (`api.stone-prd-rh01.pg1f.p1.openshiftapps.com`), tenants incl.
`open-data-hub-tenant`, `rhoai-ide-konflux-tenant`, `rhtap-integration/release-2/releng-tenant`:
- **Applications**: `opendatahub-builds` (367d), `opendatahub-release`, `odh-release`, `odh-gitops`, `odh-base-containers`, …
- **`nightly-cronjob`** (schedule `0 0 */1 * *`, daily 00:00, active): runs `quay.io/konflux-ci/appstudio-utils:latest`
  with `KONFLUX_APPLICATION_NAME=opendatahub-builds`, `KONFLUX_COMPONENT_NAME=odh-fbc-fragment-ci`; it selects the
  latest **AutoReleased** push snapshot for that component and labels it `test.appstudio.openshift.io/run=its-trigger-nightly`
  → triggering the **Integration Service (ITS) E2E scenario `its-trigger-nightly`** = the ODH nightly test run.
  (So ODH "nightly" = latest auto-released FBC-fragment snapshot + ITS scenario, fired by this cron.)
- Recent `open-data-hub-tenant` PipelineRuns are `*-on-pull-request-*` (PR builds) + `maas-group-test`.

**Note:** RHOAI component-build PipelineRuns in `rhoai-tenant` are heavily pruned (only the `conforma-*` gate runs
remained at read time); the nightly/scheduled FBC builds are driven by the `*-scheduled.yaml` PipelineRuns (verified via
`gh`/`konflux-central` in §5) and their `-nightly`-tagged output, with the resulting Snapshot feeding the §11 Release CRs.
