# Konflux

This file provides an overview and quick access links to the **Konflux** environments used for building and deploying components for the **Open Data Hub (ODH)** and **Red Hat Data Services (RHDS)** projects.

## Build system overview

[Konflux](https://konflux-ci.dev/) is Red Hat's supply-chain-security-focused CI/CD system built on Tekton. It replaced Brew/OSBS for building RHOAI container images. The build pipeline includes: git clone, dependency prefetch (Cachi2), multi-arch buildah builds, image index creation, source image creation, and security scans (Clair vulnerability, ClamAV malware, Snyk SAST, shell-check, unicode check, RPM signature scan, deprecated-base-image check). It also handles SBOM generation, Tekton Chains attestation, tagging, Slack failure notifications, and triggering downstream operator builds.

### How notebooks images are built

Each notebook image (workbench or pipeline runtime) has:
- A `Dockerfile.<variant>` (e.g., `Dockerfile.cpu`, `Dockerfile.cuda`, `Dockerfile.rocm`)
- A `Dockerfile.konflux.<variant>` twin that currently differs only in LABEL metadata
- Build-args conf files in `build-args/` (e.g., `cpu.conf`, `konflux.cpu.conf`) containing `BASE_IMAGE`, `INDEX_URL`, `PYLOCK_FLAVOR`

The Makefile selects which Dockerfile and conf file to use based on the `KONFLUX` environment variable. The conf file is parsed by awk into `--build-arg KEY=VALUE` flags (see the `build_image` function in the Makefile). In Tekton pipelines, the same conf file is passed to buildah via `--build-arg-file`.

### Pipeline generation

The `.tekton/` PipelineRun YAMLs in this repo are **generated** by `ci/cached-builds/konflux_generate_component_build_pipelines.py`. This script reads the Makefile to determine the Dockerfile path for each image target and generates both push and pull-request PipelineRun YAMLs. The generated pipelines already include an `image-labels` parameter (currently set to `release=<version>`) and a `build-args-file` parameter pointing to the appropriate conf file.

### ODH vs RHOAI pipelines

The two repos have **different Tekton pipelines** with different Dockerfile/conf file references:

- **`opendatahub-io/notebooks`** (this repo) -- `.tekton/` contains ODH-main push/PR pipelines (e.g., `*-odh-main-push.yaml`) and ODH stable push pipelines (e.g., `*-push.yaml`). These reference the standard `Dockerfile.<variant>` and `build-args/<variant>.conf`. The stable push pipelines use a shared pipeline definition from [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central/tree/main/pipeline) via a git `pipelineRef` resolver. The ODH-main pipelines embed the pipeline spec inline.
- **`red-hat-data-services/notebooks`** (the fork) -- `.tekton/` contains RHOAI push/PR pipelines synced from [red-hat-data-services/konflux-central](https://github.com/red-hat-data-services/konflux-central/tree/main/pipelineruns/notebooks/.tekton). These reference the Konflux-specific `Dockerfile.konflux.<variant>` and `build-args/konflux.<variant>.conf`.

Previously, the ODH notebook PipelineRuns lived in `odh-konflux-central/pipelineruns/notebooks/`. They were migrated back into this repo's `.tekton/` so that pipeline definition changes (e.g., resource limits, CEL trigger expressions) ship alongside the code on the `stable` branch, rather than requiring a separate PR to a central repo.

## Repository ecosystem

### [opendatahub-io/odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central)

Central configuration store for Konflux CI/CD artifacts across all ODH components (~44 components).

- **`pipeline/`** -- Shared Tekton Pipeline definitions (e.g., `multi-arch-container-build.yaml`) that define the full build-and-scan workflow. The ODH stable push pipelines in this repo's `.tekton/*-push.yaml` reference these via `pipelineRef`.
- **`pipelineruns/`** -- Per-component PipelineRun definitions. The notebooks PipelineRuns have been **migrated back** into this repo's `.tekton/` directory (see `pipelineruns/notebooks/README.md` deprecation notice), so pipeline updates sync to the `stable` branch alongside code changes.
- **`gitops/`** -- Kubernetes/Konflux resource manifests that register each component with the Konflux application (`opendatahub-builds`). `Component` CRs point to each repo's source, output image in `quay.io/opendatahub/`, and the build pipeline to use.
- **`integration-tests/`** -- Integration test configurations, including a `notebooks/` subdirectory.
- **`workflows/notebooks/`** -- Contains `insta-merge.yaml` for auto-merging notebook changes.

### [red-hat-data-services/konflux-central](https://github.com/red-hat-data-services/konflux-central)

Centralized configuration hub for the RHOAI/RHDS Konflux system (~50 components). Analogous to `odh-konflux-central` but for downstream.

- **Pipeline Sync** -- Tekton PipelineRun YAMLs are authored under `pipelineruns/<component>/.tekton/` and automatically distributed to each component repo's `.tekton/` directory via the `sync-pipelineruns.yml` GitHub Actions workflow.
- **Renovate Sync** -- Centralizes Renovate dependency-update configs, mapped via `config.yaml`, and pushed to target repos.
- **Validation and release management** -- Workflows validate PipelineRun correctness, handle release branch patterns (`rhoai-X.Y`, `rhoai-X.Y-ea.N`), apply z-stream changes, and retrigger builds.
- **Reusable Pipelines** -- `pipelines/` holds container-build, multi-arch-container-build, and fbc-fragment-build definitions.

### [red-hat-data-services/RHOAI-Konflux-Automation](https://github.com/red-hat-data-services/RHOAI-Konflux-Automation)

Release engineering toolbox for RHOAI. It is the glue between Konflux builds and RHOAI releases.

- **`utils/processors/`** -- `operator-processor.py` and `bundle-processor.py` sync operator manifests, update image digests from Quay.io, and manage Tekton push-pipeline toggles.
- **`utils/fbc-processor/`** -- Handles File-Based Catalog (FBC) operations: patching OLM catalog YAML with new bundles, remapping image registries to Red Hat production, and extracting container images from build snapshots.
- **`utils/release-helper/`** -- Shell and Python scripts that generate stage and production release artifacts, validate consistency, and automate the release sequence.
- **`utils/stage-promoter/`** -- Merges catalog patches for staging, polls Quay.io for completed FBC fragment builds, verifies image signatures, and sends Slack notifications.
- **`utils/sprint-onboarder/`** -- YAML templates defining Konflux Component resources for each RHOAI version, pointing to source repos with their Dockerfiles.
- **`utils/commons/`** -- Shared Quay.io controller/onboarder utilities and `repos.yaml` listing ~29 ODH component repos.

### [red-hat-data-services/rhods-devops-infra](https://github.com/red-hat-data-services/rhods-devops-infra)

Automated synchronization infrastructure between upstream ODH and downstream RHDS repositories.

- **[Upstream to Downstream Auto-Merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/upstream-auto-merge.yaml)** -- Runs daily at 00:00 UTC. Syncs changes from upstream repos (e.g., `opendatahub-io/notebooks`) to downstream repos (e.g., `red-hat-data-services/notebooks`) based on [upstream-source-map.yaml](https://github.com/red-hat-data-services/rhods-devops-infra/blob/main/src/config/upstream-source-map.yaml). It can also be manually triggered per component.
- **[Main to Release Auto-Merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/main-release-auto-merge.yaml)** -- Runs daily at 01:00 UTC. Syncs from downstream `main` to `rhoai-x.y` release branches based on [main-release-source-map.yaml](https://github.com/red-hat-data-services/rhods-devops-infra/blob/main/src/config/main-release-source-map.yaml). Automatically creates release branches on sprint start and disables auto-merge after code freeze.
- **Jira Ticket Automation** -- Generates sprint tickets from YAML templates via [create-jira-tickets.yaml](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/create-jira-tickets.yaml).

## Pipeline resource overrides

All PipelineRuns in `.tekton/` override compute resources for several tasks that OOM with Konflux defaults on this repo's large source tree. The standard overrides (4 CPU / 8Gi) cover `prefetch-dependencies`, `build-images`, `clair-scan`, `sast-shell-check`, `sast-unicode-check`, and `sast-snyk-check`. The codeserver pipelines use higher limits (**8 CPU / 32Gi**) for `prefetch-dependencies` and `build-images` because the codeserver image is significantly larger. This follows [Konflux: Overriding compute resources](https://konflux-ci.dev/docs/building/overriding-compute-resources/) (PipelineRun `spec.taskRunSpecs` in `.tekton`).

## ODH-io (Open Data Hub)

This section covers the Konflux setup for the upstream **Open Data Hub** community project.

project: `open-data-hub-tenant`

* **Konflux UI:** View and monitor applications, components, and pipelines running in the ODH tenant.
    * [opendatahub-release](https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/ns/open-data-hub-tenant/applications/opendatahub-release/components) — main branch components (base images, runtimes, workbenches)
    * [opendatahub-builds](https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/ns/open-data-hub-tenant/applications/opendatahub-builds/components) — stable branch (`-ci`) components
* **OpenShift Console:** Access the underlying **OpenShift** cluster for deeper insights, logs, and resource management.
    * [openshift console](https://console-openshift-console.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/k8s/cluster/projects/open-data-hub-tenant)
* **Configuration Repository (`odh-konflux-central`):** The primary source of truth for the Konflux configuration (GitOps).
    * [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central):
        * [pipelines](https://github.com/opendatahub-io/odh-konflux-central/tree/main/pipelines/notebooks): Definitions of the **Tekton** pipelines used for building and testing components (e.g., notebook images).
        * [gitops](https://github.com/opendatahub-io/odh-konflux-central/tree/main/gitops): Configuration for deployed components and End-to-End (e2e) tests.
* **Build Notifications (Slack):** Push pipeline failures are posted automatically.
    * [#odh-build-notifications](https://redhat-internal.slack.com/archives/C07ANR0T9KJ)
* **Release Data (`konflux-release-data`):** Release engineering configuration for the ODH tenant.
    * [konflux-release-data](https://gitlab.cee.redhat.com/releng/konflux-release-data)
        * [stone-prd-rh01/tenants/open-data-hub-tenant](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/tree/main/tenants-config/cluster/stone-prd-rh01/tenants/open-data-hub-tenant)

### Konflux components (notebooks)

The notebook image components live in `open-data-hub-tenant` as standalone components (no application label). Each notebook image has two components: one building from `main` and one (with `-ci` suffix) building from `stable`.

| Component pattern | Branch | Example |
|---|---|---|
| `odh-pipeline-runtime-*-py312-ubi9` | `main` | `odh-pipeline-runtime-minimal-cpu-py312-ubi9` |
| `odh-pipeline-runtime-*-py312-ubi9-ci` | `stable` | `odh-pipeline-runtime-minimal-cpu-py312-ubi9-ci` |
| `odh-workbench-jupyter-*-py312-ubi9` | `main` | `odh-workbench-jupyter-datascience-cpu-py312-ubi9` |
| `odh-workbench-jupyter-*-py312-ubi9-ci` | `stable` | `odh-workbench-jupyter-datascience-cpu-py312-ubi9-ci` |
| `odh-workbench-codeserver-*` | `main` | same pattern |
| `odh-base-image-cpu-py312-{c9s,ubi9}` | `main` | base images (no `-ci` / `stable` counterpart) |

```bash
# list all notebook components
oc get components -n open-data-hub-tenant \
  -o custom-columns=NAME:.metadata.name,BRANCH:.spec.source.git.revision \
  | grep -E 'runtime|workbench|base-image'
```

## RHDS (Red Hat Data Services / RHOAI)

This section covers the Konflux setup for the enterprise downstream **Red Hat Data Services** offering (often associated with **RHOAI - Red Hat OpenShift AI**).

project: `rhoai-tenant`

* **Konflux UI:** View and monitor applications and components specific to the RHDS tenant.
    * [automation](https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/ns/rhoai-tenant/applications/automation/components) — PR pipeline component
    * Per-release applications, e.g. [rhoai-v3-5-ea-1](https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/ns/rhoai-tenant/applications/rhoai-v3-5-ea-1/components) — push components for each release branch
    * [all applications](https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/ns/rhoai-tenant/applications)
* **OpenShift Console:** Access the underlying **OpenShift** cluster for the RHDS tenant.
    * [openshift console](https://console-openshift-console.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/k8s/cluster/projects/rhoai-tenant)
* **Configuration Repository (`konflux-central`):** GitOps repository for RHDS Konflux definitions.
    * [konflux-central](https://github.com/red-hat-data-services/konflux-central):
        * [pipelineruns](https://github.com/red-hat-data-services/konflux-central/tree/main/pipelineruns/notebooks/.tekton): Specific **PipelineRun** definitions used for execution.
* **Build Notifications (Slack):** Push pipeline failures are posted automatically.
    * [#rhoai-build-notifications](https://redhat-internal.slack.com/archives/C07ANR2U56C)
* **Release Data (`konflux-release-data`):** Release engineering configuration for the RHDS tenant.
    * [konflux-release-data](https://gitlab.cee.redhat.com/releng/konflux-release-data)
        * [stone-prod-p02/tenants/rhoai-tenant](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/tree/main/tenants-config/cluster/stone-prod-p02/tenants/rhoai-tenant)
        * [EnterpriseContractPolicy/registry-rhoai-prod.yaml](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/blob/main/config/stone-prod-p02.hjvn.p1/product/EnterpriseContractPolicy/registry-rhoai-prod.yaml)
        * [EnterpriseContractPolicy/fbc-rhoai-stage.yaml](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/blob/main/config/stone-prod-p02.hjvn.p1/product/EnterpriseContractPolicy/fbc-rhoai-stage.yaml)

## Triggering builds

### PR builds

Comment `/retest` on the pull request to retrigger all **failed** PR pipelines (successful ones are skipped). To retrigger a specific pipeline regardless of its previous outcome, use `/test <pipelinerun-name>` or `/retest <pipelinerun-name>`. See [PaC GitOps Commands](https://pipelinesascode.com/docs/guides/gitops-commands/).

The GitHub Checks tab "Re-run" button restarts **all** Konflux pipelines in the check suite, including those still running or already succeeded. There is no way to re-run a single check from the UI. The GitHub API endpoints `POST /check-runs/{id}/rerequest` and `POST /check-suites/{id}/rerequest` do not work with user tokens — classic OAuth returns 404, fine-grained PATs return 403 ("Resource not accessible by personal access token"). Checks API write access is [limited to GitHub Apps](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens); the API reference pages incorrectly list fine-grained PATs as supported ([doc bug](https://github.com/github/rest-api-description/issues/4290)).

### PR comment triggers (repo-specific)

Beyond `/retest`, PipelineRun YAMLs declare [Pipelines-as-Code trigger annotations](https://pipelinesascode.com/docs/guide/matchingevents/):

- `pipelinesascode.tekton.dev/on-event` -- event type (`pull_request`, `push`)
- `pipelinesascode.tekton.dev/on-target-branch` -- target branch filter
- `pipelinesascode.tekton.dev/on-comment` -- regex matched against PR comments (e.g. `"^/build-konflux"`)
- `pipelinesascode.tekton.dev/on-label` -- PR labels that trigger the pipeline when added
- `pipelinesascode.tekton.dev/on-cel-expression` -- CEL expression; takes priority over all the above when present
- `pipelinesascode.tekton.dev/on-path-change` -- only trigger when files matching a glob changed
- `pipelinesascode.tekton.dev/on-path-change-ignore` -- don't trigger when only these paths changed

Our push pipelines use `on-cel-expression` combining event + branch + `pathChanged()`. The PR pipelines use `on-comment`, `on-label`, `on-event`, and `on-target-branch`. For `.tekton/` file and component naming conventions (`metadata.name` contract, `-ci` suffix, service account patterns), see [`.tekton/README-odh.md`](../.tekton/README-odh.md).

**ODH (`opendatahub-io/notebooks`):**

- `/kfbuild all` -- triggers all PR build pipelines
- `/kfbuild <component-name>` -- triggers a single component, e.g. `/kfbuild odh-base-image-cpu-py312-ubi9`
- `/kfbuild <source-path>` -- triggers by source directory, e.g. `/kfbuild base-images/cpu/ubi9-python-3.12`
- `/group-test` -- triggers the integration test pipeline that tests images from the `stable` branch (see [Integration Testing guide](konflux-integration.md))

**RHDS (`red-hat-data-services/notebooks`):**

PipelineRuns live in `red-hat-data-services/notebooks@main:.tekton/`.

- `/build-konflux` -- triggers all RHDS PR build pipelines
- `/build-<image-type>` -- triggers a specific image, e.g.:
  - `/build-runtime-minimal-cpu`, `/build-runtime-datascience-cpu`
  - `/build-runtime-pytorch-cuda`, `/build-runtime-pytorch-rocm`, `/build-runtime-pytorch-llmcompressor-cuda`
  - `/build-runtime-tensorflow-cuda`, `/build-runtime-tensorflow-rocm`
  - `/build-jupyter-datascience`, `/build-codeserver`
  - `/build-workbench-jupyter-minimal-cpu`, `/build-workbench-jupyter-minimal-cuda`, `/build-workbench-jupyter-minimal-rocm`
  - `/build-tensorflow-cuda`, `/build-tensorflow-rocm`
- `kfbuild-*` labels -- PR labels also trigger builds (e.g. `kfbuild-all`, `kfbuild-runtime`, `kfbuild-workbench`, `kfbuild-cpu`, `kfbuild-cuda`, `kfbuild-rocm`, `kfbuild-pytorch`, `kfbuild-tensorflow`, etc.)

### Push builds (post-merge)

Annotate the Component resource in the Konflux namespace to trigger a new build:

```bash
# ODH (stone-prd-rh01, namespace open-data-hub-tenant)
oc annotate components/<component-name> \
  build.appstudio.openshift.io/request=trigger-pac-build \
  --overwrite=true \
  -n open-data-hub-tenant

# RHOAI (stone-prod-p02, namespace rhoai-tenant)
oc annotate components/<component-name> \
  build.appstudio.openshift.io/request=trigger-pac-build \
  --overwrite=true \
  -n rhoai-tenant
```

This requires `oc` access to the respective cluster and namespace. The annotation is consumed immediately, but the PipelineRun takes ~2 minutes to appear. The component must have PaC `state: enabled` in its build status annotation. The same action is available as the "Start new build" button in the Konflux UI.

See also: [Running Build Pipelines (Konflux docs)](https://konflux-ci.dev/docs/building/running/)

## Build trigger internals

### How trigger-pac-build works

The [build-service controller](https://github.com/konflux-ci/build-service) (`TriggerPaCBuildOldModel` in `component_build_controller_pac.go`) handles the annotation:

1. Ensures an incoming secret exists for the component
2. Updates the PaC `Repository` CR with an `incoming` webhook configuration for the component's target branch
3. POSTs to the PaC controller's `/incoming` endpoint with the pipelinerun name, branch, secret, and repository

PaC then searches `.tekton/` on the component's configured branch for a PipelineRun matching the name `<component-name>-on-push`. Incoming webhooks match PipelineRuns with `on-event: push` or `on-event: incoming` — no need to explicitly define `incoming` in the PipelineRun annotations. See [PaC Incoming Webhook docs](https://pipelinesascode.com/docs/guide/incoming_webhook/).

### Why pushing a branch may not trigger builds

The push pipelines in `.tekton/` use CEL expressions with `pathChanged()` guards, e.g.:

```text
event == "push" && target_branch == "stable" && ( "runtimes/minimal/ubi9-python-3.12/**".pathChanged() || ... )
```

A push that moves a branch pointer (e.g. `stable` to match `main`) only triggers pipelines whose `pathChanged()` patterns match the diff between the old and new branch HEAD. If no source files in those paths changed, no builds run.

### Nudge files and the `!pathChanged()` guard

Push pipelines declare a `build.appstudio.openshift.io/build-nudge-files` annotation (e.g. `manifests/base/params-latest.env`). This tells the Konflux [component dependency update controller](https://github.com/konflux-ci/build-service) which files to modify when a base image is rebuilt — the controller runs Renovate to open a PR updating image references in those files. The CEL expression **negates** the nudge file path (`!("manifests/base/params-latest.env".pathChanged())`) so that the nudge commit itself does not trigger every pipeline that lists the file; instead, only the specific downstream component's build is triggered via the nudge mechanism. See [#3518](https://github.com/opendatahub-io/notebooks/issues/3518) for known issues with stale nudge paths.

### `prefetch-input/` path watching

Most pipelines intentionally do not watch `prefetch-input/` in their CEL expressions — changing prefetched inputs will not retrigger those builds. This is deliberate: `prefetch-input/odh/` is shared across all images, and watching it would trigger 30+ simultaneous rebuilds on any change. Changes to shared prefetch inputs should be rebuilt via `/kfbuild all` or `trigger-pac-build`. See [PR #3232](https://github.com/opendatahub-io/notebooks/pull/3232) (RHAIENG-4234) which centralized prefetch inputs and removed them from triggers. A few workbench pipelines (pytorch-cuda, pytorch-rocm, trustyai) still watch image-specific paths like `prefetch-input/mongocli/**`.

### Tenant RBAC for build operations

**What tenant users CAN do:**
- Annotate components (including `trigger-pac-build`)
- Get/list/watch PipelineRuns (`tkn pipelinerun list` works)
- Stream live logs (`opc pipelinerun logs -f`) and query historical logs (`opc results`, `kubectl tekton`)

**What tenant users CANNOT do:**
- Create PipelineRuns directly (`oc create pipelinerun` → Forbidden)
- Start pipelines via `tkn pipeline start` (can't list Pipelines → Forbidden)
- Read PaC Repository CRs (`oc get repositories` → Forbidden)
- Read secrets (including incoming webhook secrets)
- List routes in `openshift-pipelines` namespace

The PaC controller's `/incoming` endpoint (`pipelines-as-code-controller-openshift-pipelines.apps.<cluster>/incoming`) is externally reachable (HTTP 200), but POSTs require the incoming secret from the Repository CR, which tenants can't read. Without the correct secret, POSTs are silently ignored.

**Workaround when `trigger-pac-build` doesn't work:** push a no-op commit touching files that match the pipeline's `pathChanged()` patterns.

## Known issues and troubleshooting

### `trigger-pac-build` name matching

The build-service controller constructs the expected PipelineRun name as `<component-name>-on-push` and searches `.tekton/` on the component's configured branch. If the `metadata.name` in the PipelineRun YAML doesn't match this pattern, the trigger silently does nothing. PR [#3511](https://github.com/opendatahub-io/notebooks/pull/3511) aligned the names; see [`.tekton/README-odh.md`](../.tekton/README-odh.md) for the naming convention.

### `trigger-pac-build` silent failures (historical)

The annotation could silently fail if PaC's `/incoming` webhook processing hit issues. This was a recognized bug ([KONFLUX-5925](https://issues.redhat.com/browse/KONFLUX-5925), now closed). The "Start new build" UI button uses the same mechanism. After PR #3511 aligned PipelineRun names with component names, both the annotation and the UI button work correctly (confirmed 2026-05-05, [Slack](https://redhat-internal.slack.com/archives/C096ZR053RQ/p1777994830781979?thread_ts=1777993828.466429&cid=C096ZR053RQ)).

### Component delete/recreate race condition (Argo)

Deleting and recreating a Konflux component too closely together (as happens during Argo GitOps reconciliation) can leave PaC in a broken state where builds don't trigger from PRs and/or the `trigger-pac-build` annotation / UI button stops working. Workaround: ensure sufficient delay between delete and recreate, or manually re-enable PaC.

## Pipeline improvement tracking

Open issues for `.tekton/` pipeline improvements identified during trigger investigation:

- [#3512](https://github.com/opendatahub-io/notebooks/issues/3512) — `image-expires-after` for main push builds
- [#3515](https://github.com/opendatahub-io/notebooks/issues/3515) — Hermeto/cachi2 automatic env injection evaluation
- [#3517](https://github.com/opendatahub-io/notebooks/issues/3517) — stable push pipeline serviceAccountName alignment
- [#3518](https://github.com/opendatahub-io/notebooks/issues/3518) — stale nudge paths in CEL guards
- [#3519](https://github.com/opendatahub-io/notebooks/issues/3519) — missing clair-scan/ecosystem-cert taskRunSpecs in main push
- [#3520](https://github.com/opendatahub-io/notebooks/issues/3520) — hermetic builds for stable-branch push pipelines
- [#3521](https://github.com/opendatahub-io/notebooks/issues/3521) — drop `-odh-main-` infix from base image pipeline filenames

## CLI tools

**`opc` (OpenShift Pipelines Client)** — bundles Tekton CLI + PaC CLI + Results CLI. Install: `brew tap openshift-pipelines/opc https://github.com/openshift-pipelines/opc && brew install opc`.

Useful local commands (no cluster access needed):

- `opc pac resolve -f .tekton/my-pipeline.yaml -p revision=main -p repo_url=...` — resolve a PipelineRun locally with remote tasks embedded and parameter substitutions applied. Useful for validating pipeline YAML before pushing.
- `opc pac cel -b payload.json -H headers.json` — evaluate CEL expressions interactively against real webhook payloads. Useful for testing `pathChanged()` and trigger expressions locally.

Useful cluster commands (read-only, works with tenant RBAC):

- `opc pipelinerun logs -f <name> -n <namespace>` — stream live logs from a running PipelineRun
- `opc results pipelinerun list -n <namespace>` — query historical PipelineRuns after pod garbage collection

**`opc assist pipelinerun diagnose`** — AI-powered failure diagnosis. Requires an OpenShift Lightspeed (OLS) backend (`--lightspeed-url`, defaults to `localhost:8443`). OLS is not deployed on the Konflux production clusters (stone-prd-rh01, stone-prod-p02) as of 2026-05-05. The request format is OLS-specific (`POST /v1/query`), not OpenAI-compatible. The Pipelines team is moving toward OLS as the standard AI integration point ([Slack](https://redhat-internal.slack.com/archives/CG5GV6CJD/p1759933574593019), [demo](https://redhat-internal.slack.com/archives/CG5GV6CJD/p1760349713133729)).

For detailed log fetching procedures (opc results, kubectl-tekton, curl API, kubearchive), see the [internal guide](https://gitlab.cee.redhat.com/data-hub/guide/-/tree/main/docs/notebooks/konflux).

## Automations (Upstream/Downstream Flow)

These GitHub Actions workflows manage the automated synchronization of configurations between the upstream ODH community repositories and the downstream RHDS/RHOAI repositories, ensuring a smooth flow of changes and releases.

* **ODH-io -> RHDS Auto-Merge (Upstream to Downstream):** Automatically merges approved changes from ODH upstream configurations into the RHDS central configuration repository.
    * [ODH-io -> RHDS auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/upstream-auto-merge.yaml)
* **RHDS/main -> RHOAI-* Auto-Merge (Release Propagation):** Manages the promotion of changes from the main RHDS branch to specific release branches (e.g., `rhoai-vX.Y`), facilitating new product releases.
    * [RHDS/main -> rhoai-* auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/main-release-auto-merge.yaml)
* **ODH main -> stable Auto-Merge:** Merges `main` into `stable` for the notebooks repo (RHOAIENG-60781).
    * [main -> stable auto-merge](https://github.com/opendatahub-io/notebooks/actions/workflows/merge-main-to-stable-fast-forward.yaml)

## Dockerfile deduplication

The repo has ~59 Dockerfiles with two axes of duplication:
1. **ODH vs Konflux** -- every `Dockerfile.<variant>` has a `Dockerfile.konflux.<variant>` twin that differs only in LABEL metadata (~21 Konflux files)
2. **cpu/cuda/rocm variants** -- within the same directory, these are ~95% identical

Tracking issues:
- GitHub: [opendatahub-io/notebooks#3355 -- Dockerfile Deduplication Plan](https://github.com/opendatahub-io/notebooks/issues/3355)
- Jira: [RHOAIENG-54488 -- Merge Dockerfiles into single unified Dockerfile per component](https://issues.redhat.com/browse/RHOAIENG-54488)

**Phase 1** (Konflux dedup): Parameterize LABEL blocks via build-args so `Dockerfile.cpu` and `Dockerfile.konflux.cpu` become byte-identical. The CI alignment check (`scripts/check_dockerfile_alignment.sh`) already verifies semantic identity; the goal is to achieve byte-identity.

**Phase 2** (variant merge): Merge cpu/cuda/rocm variants into a single Dockerfile per component using build-args for the accelerator-specific differences. Only 3 directories have multiple variants to merge (`jupyter/minimal`, `rstudio/c9s-python-3.12`, `rstudio/rhel9-python-3.12`).

## Future direction: E2E TestOps ecosystem

The [E2E TestOps Ecosystem across ODH & RHOAI](https://docs.google.com/document/d/1LNkQDDN1g--3UYmLzi_c8WZjNSNudzDmhRrqQ7IaDeM/edit) design document (Jira: [RHAISTRAT-903](https://issues.redhat.com/browse/RHAISTRAT-903), status: In-Progress, created Dec 2025) defines a phased plan to standardize the entire TestOps ecosystem across ODH and RHOAI. The document has 9 tabs covering:

1. **Design + Plan** -- Architecture with five logical planes (Orchestration, Test Selection, Test Execution, Reporting, Gating) and a Knowledge Layer. Six phases from actionable reporting (Phase 1, target end Apr 2026) through AI-driven optimization (Phase 6).
2. **Redefining CI Quality Gate Strategy** -- Proposes a fail-fast model: Cluster Verification Test (CVT) and Build Verification Test (BVT) first (~15 min), then Smoke (~1-2h), then Tier 1/2/3 (~5-10h).
3. **CI Build Test Failure Response Framework** -- Defines failure ownership (automation issue vs product issue), SLAs (24h triage), and fix-vs-revert strategy across Stream/Lake/Ocean stages.
4. **TestOps Downstream Release Testing** -- Nightly (daily smoke, weekly deep) and RC quality gates with pass/fail criteria for promotion.
5. **Test Infrastructure & Quality Gate Strategy** -- Maps test gates to Stream (dev sandbox), Lake (ODH integration), and Ocean (RHOAI integration) stages of the Bodies of Water framework.
6. **ODH Nightly Pipeline Ownership & Triage** -- Weekly on-call rotation for ODH nightly smoke pipeline triage, automated via Slack bot.
7. **Component-Based Pipelines in Jenkins CI** -- Standardized per-component Jenkins pipelines (implemented via [RHOAIENG-43188](https://issues.redhat.com/browse/RHOAIENG-43188)).
8. **Test Reporting System** -- Bot-based architecture using Data Router + ReportPortal as central hub, with Jira TFA integration and Slack notifications.
9. **Sign-off** -- Team sign-off tracking.
