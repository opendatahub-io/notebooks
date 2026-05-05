# Konflux

This file provides an overview and quick access links to the **Konflux** environments used for building and deploying components for the **Open Data Hub (ODH)** and **Red Hat Data Services (RHDS)** projects.

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

## Manually triggering builds

### Retrigger a PR (pre-merge) build

Comment `/retest` on the pull request to retrigger all failed PR pipelines. To retrigger a specific pipeline, use `/retest <pipelinerun-name>`.

### Repo-specific PR comment triggers

Beyond `/retest`, PipelineRun YAMLs declare [Pipelines-as-Code trigger annotations](https://pipelinesascode.com/docs/guide/matchingevents/):

- `pipelinesascode.tekton.dev/on-event` -- event type (`pull_request`, `push`)
- `pipelinesascode.tekton.dev/on-target-branch` -- target branch filter
- `pipelinesascode.tekton.dev/on-comment` -- regex matched against PR comments (e.g. `"^/build-konflux"`)
- `pipelinesascode.tekton.dev/on-label` -- PR labels that trigger the pipeline when added
- `pipelinesascode.tekton.dev/on-cel-expression` -- CEL expression; takes priority over all the above when present
- `pipelinesascode.tekton.dev/on-path-change` -- only trigger when files matching a glob changed
- `pipelinesascode.tekton.dev/on-path-change-ignore` -- don't trigger when only these paths changed

Our push pipelines use `on-cel-expression` combining event + branch + `pathChanged()`. The PR pipelines use `on-comment`, `on-label`, `on-event`, and `on-target-branch`. For `.tekton/` file and component naming conventions (`metadata.name` contract, `-ci` suffix, service account patterns), see [`.tekton/README-odh.md`](../.tekton/README-odh.md).

The triggers defined in this repo:

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

### Retrigger a push (post-merge) build

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

This requires `oc` access to the respective cluster and namespace. The annotation is consumed immediately, but the PipelineRun takes ~2 minutes to appear. The component must have PaC `state: enabled` in its build status annotation.

See also: [Running Build Pipelines (Konflux docs)](https://konflux-ci.dev/docs/building/running/)

#### How trigger-pac-build works internally

The [build-service controller](https://github.com/konflux-ci/build-service) (`TriggerPaCBuildOldModel` in `component_build_controller_pac.go`) handles the annotation:

1. Ensures an incoming secret exists for the component
2. Updates the PaC `Repository` CR with an `incoming` webhook configuration for the component's target branch
3. POSTs to the PaC controller's internal `/incoming` endpoint with the pipelinerun name, branch, secret, and repository

PaC then searches `.tekton/` on the component's configured branch for a PipelineRun matching the name `<component-name>-on-push`. Incoming webhooks match PipelineRuns with `on-event: push` or `on-event: incoming` — no need to explicitly define `incoming` in the PipelineRun annotations. See [PaC Incoming Webhook docs](https://pipelinesascode.com/docs/guide/incoming_webhook/).

Users cannot curl the `/incoming` endpoint directly — it's an internal cluster route, and the incoming secret is not readable with tenant-level RBAC. The `trigger-pac-build` annotation is the intended user-facing abstraction.

Previously this mechanism was broken ([KONFLUX-5925](https://issues.redhat.com/browse/KONFLUX-5925), now closed).

### Why pushing a branch may not trigger builds

The push pipelines in `.tekton/` use CEL expressions with `pathChanged()` guards, e.g.:

```text
event == "push" && target_branch == "stable" && ( "runtimes/minimal/ubi9-python-3.12/**".pathChanged() || ... )
```

A push that moves a branch pointer (e.g. `stable` to match `main`) only triggers pipelines whose `pathChanged()` patterns match the diff between the old and new branch HEAD. If no source files in those paths changed, no builds run.

See also: [Running Build Pipelines (Konflux docs)](https://konflux-ci.dev/docs/building/running/)

## ⚙️ Automations (Upstream/Downstream Flow)

These GitHub Actions workflows manage the automated synchronization of configurations between the upstream ODH community repositories and the downstream RHDS/RHOAI repositories, ensuring a smooth flow of changes and releases.

* **ODH-io -> RHDS Auto-Merge (Upstream to Downstream):** Automatically merges approved changes from ODH upstream configurations into the RHDS central configuration repository.
    * [ODH-io -> RHDS auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/upstream-auto-merge.yaml)
* **RHDS/main -> RHOAI-* Auto-Merge (Release Propagation):** Manages the promotion of changes from the main RHDS branch to specific release branches (e.g., `rhoai-vX.Y`), facilitating new product releases.
    * [RHDS/main -> rhoai-* auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/main-release-auto-merge.yaml)
* **ODH main -> stable Auto-Merge:** Merges `main` into `stable` for the notebooks repo (RHOAIENG-60781).
    * [main -> stable auto-merge](https://github.com/opendatahub-io/notebooks/actions/workflows/merge-main-to-stable-fast-forward.yaml)
