---
name: konflux-analyze
description: Investigate Konflux pipeline failures on a GitHub PR — fetch the PR check runs, identify failed Konflux checks, extract PipelineRun names and cluster info, query KubeArchive (with Tekton Results fallback) for each failed PipelineRun and TaskRun, categorize failure modes, and report a verdict (infrastructure issue vs PR-related failure). Use when asked to analyze why a PR's Konflux checks failed or to triage multiple failing pipeline runs on a PR; do not use to inspect a single named PipelineRun by URL or name (use the konflux-logs skill).
---

# Konflux PR Failure Analysis

Investigate Konflux pipeline failures on a GitHub PR. The user provides a PR
number or URL for the opendatahub-io/notebooks repo (or another repo), e.g.
`3569` or `https://github.com/opendatahub-io/notebooks/pull/3569`.

## Steps

### 1. Fetch PR check runs

Get all checks for the PR (GitHub MCP `pull_request_read` with method
`get_check_runs`, or `gh pr checks <number> --repo <repo>`). Identify the
failed checks — look for checks whose name contains "Konflux" or
"Red Hat Konflux" with `conclusion: "failure"`.

If there are no Konflux failures, report that and stop.

### 2. Extract PipelineRun names and cluster info

From each failed check's `detailsUrl`, extract:

- **Cluster**: from the URL domain (e.g., `stone-prd-rh01` or `stone-prod-p02`)
- **Namespace**: from the URL path (e.g., `open-data-hub-tenant` or `rhoai-tenant`)
- **PipelineRun name**: from the URL path (the last path segment)

Use this mapping for clusters and namespaces:

| Component (upstream / downstream)            | Cluster         | Namespace              |
| -------------------------------------------- | --------------- | ---------------------- |
| ODH notebooks (opendatahub-io)               | stone-prd-rh01  | `open-data-hub-tenant` |
| RHOAI notebooks (red-hat-data-services)      | stone-prod-p02  | `rhoai-tenant`         |

### 3. Verify cluster access

Check that the user has a valid `oc` context for the target cluster:

```bash
KONFLUX_CTX="$(oc config get-contexts -o name | grep <cluster-name> | head -1)"
oc whoami --context="$KONFLUX_CTX"
```

If the token is expired, run `oc login --web` directly (don't just tell the
user to do it):

```bash
oc login --web --server=https://api.<cluster-domain>:6443 --context="$KONFLUX_CTX"
```

### 4. Query KubeArchive for each failed PipelineRun

For each failed PipelineRun, query the KubeArchive API for:

**a) PipelineRun status:**

```bash
TOKEN="$(oc whoami -t --context="$KONFLUX_CTX")"
KA_HOST="https://kubearchive-api-server-product-kubearchive.apps.<cluster-domain>"

curl -s --max-time 30 -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/$NS/pipelineruns/$PIPELINERUN" | \
  jq '{name: .metadata.name, status: .status.conditions}'
```

**b) TaskRun statuses (non-succeeded only):**

```bash
curl -s --max-time 30 -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/$NS/taskruns?labelSelector=tekton.dev/pipelineRun=$PIPELINERUN&limit=50" | \
  jq '[.items[] | {task: .metadata.labels["tekton.dev/pipelineTask"], status: .status.conditions[0].reason, message: .status.conditions[0].message}] | map(select(.status != "Succeeded"))'
```

Run queries for independent PipelineRuns in parallel (multiple shell calls
in one message) to save time.

### 5. Categorize failure modes

For each failed TaskRun, classify the failure:

- **PodCreationFailed** with "resource quota evaluation timed out" →
  cluster resource quota pressure (infrastructure issue)
- **PodCreationFailed** with "exceeded quota" → namespace quota limit
  reached (infrastructure issue)
- **TaskRunCancelled** with "PipelineRun ... has timed out" → secondary
  failure from pipeline timeout
- **Failed** with step error → actual task failure (may be PR-related)
- **TaskRunImagePullFailed** → image registry issue

### 6. Report findings

Produce a summary with:

- A clear verdict: infrastructure issue vs. PR-related failure
- A per-pipeline table showing: pipeline name, timeout duration, failed
  task(s), failure mode
- Key observations (e.g., "all build-images tasks succeeded", "resource
  quota pressure on cluster")
- Recommendation (re-trigger, fix code, etc.)

## KubeArchive host mapping

| Cluster        | KubeArchive Host                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------------------- |
| stone-prd-rh01 | `kubearchive-api-server-product-kubearchive.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com`                 |
| stone-prod-p02 | `kubearchive-api-server-product-kubearchive.apps.stone-prod-p02.hjvn.p1.openshiftapps.com`                 |
| kflux-prd-rh02 | `kubearchive-api-server-product-kubearchive.apps.kflux-prd-rh02.0fk9.p1.openshiftapps.com`                 |
| kflux-prd-rh03 | `kubearchive-api-server-product-kubearchive.apps.kflux-prd-rh03.nnv1.p1.openshiftapps.com`                 |

## Tekton Results fallback

If KubeArchive returns empty results, fall back to Tekton Results:

| Cluster        | Tekton Results Host                                                                    |
| -------------- | -------------------------------------------------------------------------------------- |
| stone-prd-rh01 | `tekton-results-tekton-results.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com`           |
| stone-prod-p02 | `tekton-results-tekton-results.apps.stone-prod-p02.hjvn.p1.openshiftapps.com`           |

```bash
HOST="tekton-results-tekton-results.apps.<cluster-domain>"
curl -s --max-time 60 -H "Authorization: Bearer $TOKEN" \
  "https://${HOST}/apis/results.tekton.dev/v1alpha2/parents/${NS}/results/-/records?filter=data.metadata.name==%22${PIPELINERUN}%22&page_size=5&fields=records.name"
```
