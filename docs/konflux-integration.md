# Konflux Integration Testing

This document covers Konflux group testing for the notebooks repo — how to trigger it, how images are resolved, workspace sharing pitfalls, ephemeral cluster provisioning, and operational debugging. For basic Konflux setup, links, and resource overrides, see [konflux.md](konflux.md).

**Documentation links:**

- [Konflux public docs](https://konflux-ci.dev/docs/)
- [Konflux internal docs](https://konflux.pages.redhat.com/docs/users/) (Red Hat VPN required)
- [Ephemeral OpenShift clusters in Konflux CI](https://developers.redhat.com/articles/2024/10/28/ephemeral-openshift-clusters-konflux-ci-using-cluster-service-operator)
- [EaaS step actions](https://github.com/konflux-ci/build-definitions/tree/main/stepactions) (`eaas-*` step actions)
- [generate-snapshot task](https://github.com/red-hat-data-services/rhoai-konflux-tasks/tree/main/konflux-tekton-tasks/generate-snapshot-for-group-testing)

## Group-Test Pipeline

**Files:**

- `.tekton/notebooks-group-test.yaml` — PipelineRun (trigger config, workspace bindings, component list)
- `.tekton/notebooks-group-testing-pipeline.yaml` — Pipeline definition (task graph, test scripts)

**Trigger:** Only on `/group-test` PR comment or `event == "group-test"` CEL expression. Never auto-triggers on push or PR creation.

**Pipeline stages:**

1. `generate-snapshot` — resolves images for all 18 components from Quay
2. `audit-snapshot` — prints the resolved snapshot for verification
3. `provision-eaas-space` — provisions an EaaS namespace on the management cluster
4. `provision-cluster` — creates a HyperShift cluster on AWS (10–20 min)
5. `deploy-and-test` — clones the PR's repo (for Makefile/test harness), then for each workbench: deploys to the cluster, runs tests, undeploys

**Error handling:** The `deploy-and-test` step deliberately does **not** use `set -e`. Each workbench runs inside a `run_workbench_test` helper that captures failures via `|| ((FAILURES++))`. All workbenches are attempted regardless of individual failures, and a summary (PASS/FAIL per workbench) is printed at the end. The step exits with the failure count.

**Reference:** The same pattern is used by kubeflow, kserve, and feast in [odh-konflux-central/integration-tests/](https://github.com/opendatahub-io/odh-konflux-central/tree/main/integration-tests).

## Triggering: Manual Today, Automation Options

The group-test pipeline is currently **manual-only** for notebooks. No `IntegrationTestScenario` with `component_group` context exists for the notebooks application. The `event == "group-test"` CEL expression would catch automatic Konflux group snapshot events if one were configured, but none exists today.

All kubeflow group-test runs are triggered by `rhods-ci-bot` posting `/group-test` comments — a bot automation, not Konflux-native.

**Options to automate:**

1. **Type `/group-test` manually** on each PR
2. **Ask `rhods-ci-bot` maintainers** to add notebooks to the bot's config — this is how kubeflow does it. The bot is likely configured in `rhods-devops-infra` (same repo that hosts the auto-merge workflows referenced in `docs/konflux.md`). Least effort if it's just a config addition.
3. **GitHub Action** — add a workflow triggered on `check_suite` / `status` events that posts `/group-test` via `gh pr comment` after all component builds succeed
4. **Prow plugin** — the repo already uses Prow for `tide`; a trigger could post the comment
5. **IntegrationTestScenario** — create one with `component_group` context for the notebooks Konflux application for native automatic triggering (Konflux-native, no bot needed)

## How generate-snapshot Resolves Images

The `generate-snapshot` task (from [rhoai-konflux-tasks](https://github.com/red-hat-data-services/rhoai-konflux-tasks)) resolves images for each component:

1. Constructs tag `odh-pr-<PR_NUMBER>` from the PipelineRun's PR metadata
2. Checks Quay via `skopeo inspect docker://quay.io/<repo>:<tag>`
3. If the PR image exists, uses it (newly built). Otherwise falls back to the `odh-stable` tag.
4. Queries the Quay API for the image digest and extracts `git.url` / `git.commit` labels from the image metadata

**Implication:** On a manual `/group-test` trigger for a non-build PR (e.g., only `.tekton/` changes), all components fall back to stable images. On a real build PR, rebuilt components get their PR-specific images.

**Changed vs reused:** The snapshot JSON distinguishes them. Components with populated `git.url`/`git.commit` were rebuilt for the PR; those with empty values are reused stable images. The `image_tag` field shows `odh-pr-<N>` vs `odh-stable`.

**Empty `git.url` fallback:** When a component wasn't rebuilt, its `git.url` and `git.commit` are empty. The `deploy-and-test` script needs a repo to clone for the Makefile and test harness (deploy manifests, test scripts), so it falls back to the PR's own `{{repo_url}}` and `{{revision}}` (passed as pipeline params `repo-url` and `revision` from PaC template variables). This ensures tests always run against the PR's source tree.

## Future: Test Only Modified Images

The `git.url`/`git.commit` fields in the snapshot make it possible to test only images that actually changed in a PR. Today the `deploy-and-test` task tests a hardcoded list of 5 workbenches regardless of what changed.

Since notebook workbench images are independent of each other, a future improvement could:

- Use the snapshot to identify which components have `odh-pr-<N>` tags (i.e., were rebuilt)
- Start only those workbenches in the ephemeral cluster
- Run tests for each independently, in parallel
- Use a long pipeline timeout so that regardless of scheduling order, each workbench gets tested

This would reduce test time and cluster resource usage on PRs that only touch a subset of images.

## Test Execution Patterns

Different ways to run tests against built images in Konflux:

| Pattern | How | Pros | Cons |
|---------|-----|------|------|
| **EaaS ephemeral cluster** (current) | Provision HyperShift cluster, deploy via `make deploy9-*` | Full OCP environment, closest to production | 10–20 min provisioning overhead |
| **Built image as step image** | Set `image:` in a Tekton step to the built container image | Zero provisioning, instant | No cluster API, no privileged ops, no systemd |
| **Pod in tenant namespace** | `oc run` or create a Job with the built image in the tenant namespace | No cluster provisioning, fast | Shared namespace, quotas, limited permissions |
| **`mapt` kind cluster** | Use `mapt` to create a kind cluster on AWS spot | Lighter than HyperShift, cost-efficient (spot) | Needs AWS creds + RBAC, not full OCP |
| **Podman-in-container** | Run `podman run` inside a Tekton step | Familiar local dev pattern | **Does not work** — `uid_map: operation not permitted` in non-privileged pods |

For notebooks, workbench images just need to start and respond to HTTP — using them as step images or deploying as pods could work for basic smoke tests without the EaaS overhead.

> Slack reference for podman limitation: [#konflux-users thread](https://redhat-internal.slack.com/archives/C04PZ7H0VA8/p1699465927213399)

### `mapt` Kind Cluster Details

[Task catalog](https://github.com/konflux-ci/tekton-integration-catalog/tree/main/tasks/mapt-oci/kind-aws-spot/provision/0.2) — creates a single-node Kubernetes (kind) cluster on an AWS spot instance via the [Mapt CLI](https://github.com/redhat-developer/mapt).

**Configurable:** arch (`x86_64`/`arm64`), cpus (default 16), memory (default 64 GiB), k8s version, spot pricing, nested virt, auto-destroy timeout.

**Requirements:**

1. AWS credentials in a Secret named `konflux-test-infra` (keys: `access-key`, `secret-key`, `region`, `bucket`)
2. RBAC: the pipeline ServiceAccount needs a Role with `get`, `list`, `create`, `patch` on Secrets (to create the kubeconfig Secret)
3. OCI artifact storage credentials (for task log artifacts)

The `konflux-integration-runner` SA now supports mapt (STONEINTG-1215, resolved).

Other provisioning options in the same catalog: [ROSA HCP](https://github.com/konflux-ci/tekton-integration-catalog/tree/main/tasks/rosa/hosted-cp/rosa-hcp-provision/0.2), [OpenShift CI provisioning](https://konflux-ci.dev/docs/testing/integration/third-parties/openshift-ci/).

> Slack reference: [#konflux-users thread](https://redhat-internal.slack.com/archives/C04PZ7H0VA8/p1763739323318549)

## Workspace Sharing Between Tekton Tasks

> **Key finding:** `emptyDir` is per-task, not shared across tasks. Each task in a PipelineRun gets its own emptyDir volume. Data written by one task is invisible to the next.

Use `volumeClaimTemplate` to create a real PVC shared across all tasks in a pipeline run. This is what the notebooks group-test pipeline uses for `shared-data`.

**Why this matters:** Tekton results are limited to 4KB. The snapshot JSON for 18 notebook components exceeds this. The `generate-snapshot` task detects this and falls back to writing to the `shared-data` workspace file, setting the result to the file path. Downstream tasks must check if `SNAPSHOT` is a file path and `cat` it before parsing as JSON.

**Why kubeflow works without shared-data:** It only has 2 components, so the snapshot fits in a 4KB Tekton result.

**Workarounds for sharing data in Konflux integration tests** (from [Slack #forum-dno-datarouter](https://redhat-internal.slack.com/archives/C06Q4M84XDG/p1759327188553769)):

1. Combine steps into a single task (steps share emptyDir at `/workspace`)
2. Use OCI Trusted Artifacts (push/pull via registry)
3. Use Tekton results (under 4KB only)
4. Clone source code inside the task

## Ephemeral Cluster Provisioning (EaaS)

**Cluster type:** HyperShift on AWS (`clusterTemplateRef: hypershift-aws-cluster`), 3 worker nodes, hosted control plane.

**Provisioning flow:**

1. `provision-eaas-space` — creates an `eaas.konflux-ci.dev/v1alpha1 Namespace` claim in the tenant, owned by the PipelineRun (auto-deleted when PipelineRun is cleaned up)
2. `provision-cluster` — three steps:
   - `get-supported-versions` — queries EaaS for available OCP versions (e.g., 4.14–4.20)
   - `pick-version` — picks latest patch of the newest major (e.g., `4.20.20`); configurable via `prefix` param (change `versions[0]` to `versions[2]` for an older major)
   - `create-cluster` — creates a `ClusterTemplateInstance`, waits up to 30min for provisioning

**Configurable parameters** (in the pipeline YAML):

| Parameter | Description | Default | Notebooks uses |
|-----------|-------------|---------|----------------|
| `instanceType` | AWS EC2 type | `m6g.large` | `m5.2xlarge` |
| `version` | OCP version string | (auto-selected) | latest 4.x |
| `timeout` | Provisioning wait | `30m` | `30m` |
| `fips` | Enable FIPS mode | `false` | `false` |
| `imageContentSources` | Alternate registry mirrors | `""` | `""` |

Supported instance types: `m5.large`, `m5.xlarge`, `m5.2xlarge`, `m6g.large`, `m6g.xlarge`, `m6g.2xlarge`.

**Provisioning time:** typically 10–20 minutes.

**Cleanup:** automatic — the EaaS Namespace claim is owned by the PipelineRun, so deletion of the PipelineRun triggers cluster teardown.

**Quota:** managed by the CaaS Operator at the namespace level; specific limits for `open-data-hub-tenant` not directly queryable without admin access.

## Interactive Access to Ephemeral Clusters

The `get-kubeconfig` step in `deploy-and-test` writes kubeconfig, username, password, and API server URL to the `/credentials/` volume. To connect interactively while the pipeline is running:

1. **Print credentials in logs** — the [konflux-pipeline-samples](https://github.com/rh-api-management/konflux-pipeline-samples/blob/main/pipelines/integration/deploy-operator.yaml) repo includes a `show-creds-for-debugging` step that dumps kubeconfig/password/API URL to the pipeline logs. Copy-paste locally and `oc login` — the cluster is on AWS and reachable from the internet.
2. **`oc exec` into the pod** — while `deploy-and-test` is running, exec into the pod and use the mounted kubeconfig. Requires exec permissions in `open-data-hub-tenant`.
3. **`mapt` SSH** — when using the `mapt` kind provisioner, set `ssh-credentials-secret-name` to get a Secret with `host`, `username`, and `id_rsa` for SSH access to the underlying VM. Mapt generates the keypair; you don't provide your own.

The cluster is destroyed when the PipelineRun is cleaned up, so credentials are short-lived.

> **Note:** `oc exec` into the pod requires `pods/exec` permission in `open-data-hub-tenant`, which regular users don't have. The API server URL is visible in the `get-kubeconfig` step logs, but the admin password is only on the pod's filesystem. To make interactive access work, add a `show-creds-for-debugging` step that prints the kubeconfig and password to the logs — then copy-paste locally.

## Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `workspace shared-data not provided and unable to write tekton result` | Snapshot > 4KB and no shared-data workspace provided | Add `shared-data` workspace with `volumeClaimTemplate` in the PipelineRun |
| `RequiredWorkspaceMarkedOptional` | taskSpec declares workspace as required but pipeline declares it optional | Add `optional: true` to the workspace in taskSpec |
| `parse error: Invalid numeric literal` in jq | `SNAPSHOT` env var contains a file path, not JSON | Check if `SNAPSHOT` is a file path with `-f` and `cat` it before parsing |
| Pipeline doesn't trigger on `/group-test` | PipelineRun not in `.tekton/` or wrong annotation | Ensure `.tekton/` contains the PipelineRun with `pipelinesascode.tekton.dev/on-comment: "^/group-test"` |

## Debugging Pipeline Runs

```bash
# List pipeline runs by name
oc get pipelinerun -n open-data-hub-tenant \
  -l pipelinesascode.tekton.dev/original-prname=notebooks-group-test

# Check task status
oc get taskrun <taskrun-name> -n open-data-hub-tenant \
  -o jsonpath='{.status.conditions[0]}' | python3 -m json.tool

# Get task logs (pods are ephemeral — grab logs quickly)
oc logs <pod-name> -c step-<step-name> -n open-data-hub-tenant

# For archived runs, use kubearchive REST API
export KA_HOST="https://kubearchive-api-server-product-kubearchive.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com"
export TOKEN=$(oc whoami -t)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/open-data-hub-tenant/pipelineruns?labelSelector=pipelinesascode.tekton.dev/original-prname%3Dnotebooks-group-test&limit=5"
```

## Stable vs Main Branch Sync

`stable` is a lagging branch of `main`, periodically synced via merge PRs.

**add/add conflicts** occur when `.tekton/` pipeline files don't exist in the merge base — both branches independently created them, so git can't do a 3-way merge. The resolution is to pre-apply the conflicting changes to `stable` before the merge (e.g., take `origin/main`'s version of the conflicting files).

After a main-to-stable merge, `stable` may have extra files for older base image variants (e.g., cuda 12.8, rocm 6.3 pipelines) that `main` no longer tracks.
