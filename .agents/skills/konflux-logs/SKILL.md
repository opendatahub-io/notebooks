---
name: konflux-logs
description: Check the status, task breakdown, and build logs of a specific Konflux PipelineRun by Konflux UI URL or PipelineRun name — parse the URL (cluster, namespace, name), verify oc access, query the live cluster or fall back to KubeArchive, drill into TaskRun/step-level details and pod logs, and cross-reference GitHub PR checks. Use when asked to check, debug, or fetch logs for one specific Konflux pipeline run; do not use to find which checks failed on a PR (use the konflux-analyze skill).
---

# Konflux PipelineRun Logs

Check the status and logs of a specific Konflux PipelineRun. The user
provides a Konflux UI URL or a bare PipelineRun name.

Examples:

- `https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/ns/open-data-hub-tenant/applications/opendatahub-release/pipelineruns/odh-workbench-jupyter-universal-cpu-py312-ubi9-on-pull-reqnwj8d`
- `odh-workbench-jupyter-universal-cpu-py312-ubi9-on-pull-reqnwj8d`

## Steps

### 1. Parse the input

Extract from the URL (or ask the user if only a bare name is given):

- **Cluster domain**: e.g. `stone-prd-rh01.pg1f.p1.openshiftapps.com`
- **Namespace**: e.g. `open-data-hub-tenant`
- **PipelineRun name**: the last path segment (strip trailing `/`)

If only a name is provided without a URL, infer based on naming conventions:

- Names containing `on-pull-req` or `on-push` with `odh-` prefix and namespace
  `open-data-hub-tenant` → cluster `stone-prd-rh01`
- Names with `-v2-25`, `-v3-3`, `-v3-4`, `-v3-5` suffixes in `rhoai-tenant`
  → cluster `stone-prod-p02`
- Ask the user if ambiguous

### 2. Verify cluster access

```bash
oc whoami --context "$(oc config get-contexts -o name | grep <cluster-short-name> | head -1)" 2>&1
```

If the token is expired, run `oc login --web` directly (don't just tell the
user to do it):

```bash
oc login --web https://api.<cluster-domain>:6443
```

This opens a browser for SSO. Wait for it to complete (use a 120s timeout).

### 3. Try the live cluster first

```bash
oc get pipelinerun $PIPELINERUN -n $NAMESPACE -o json
```

If it returns `NotFound`, the PipelineRun was garbage-collected — fall
through to step 4.

If found, parse and display:

- Overall status (Succeeded/Failed/Running) and message
- List of child task references with their names
- Then jump to step 5

### 4. Fall back to KubeArchive

KubeArchive hosts by cluster:

| Cluster        | KubeArchive Host                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------------------- |
| stone-prd-rh01 | `kubearchive-api-server-product-kubearchive.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com`                 |
| stone-prod-p02 | `kubearchive-api-server-product-kubearchive.apps.stone-prod-p02.hjvn.p1.openshiftapps.com`                 |

```bash
TOKEN=$(oc whoami -t)
KA_HOST="https://kubearchive-api-server-product-kubearchive.apps.<cluster-domain>"
curl -sS --max-time 15 -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/$NS/pipelineruns/$PIPELINERUN"
```

Parse the same fields as step 3. KubeArchive returns the full PipelineRun
object including status.

### 5. Get task-level details

From the PipelineRun's `.status.childReferences[]`, identify which tasks ran
and their names. Then for each task (prioritize `prefetch-dependencies` and
`build-images` as the most common failure points):

**If on the live cluster:**

```bash
oc get taskrun $TASKRUN_NAME -n $NAMESPACE -o json
```

**If via KubeArchive:**

```bash
curl -sS --max-time 15 -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/$NS/taskruns/$TASKRUN_NAME"
```

For each TaskRun, extract:

- `.status.conditions[0]` → Succeeded/Failed/Running and reason
- `.status.steps[]` → per-step exit codes and status
- `.status.podName` → needed for log retrieval

Focus on failed tasks first. Run queries for independent tasks in parallel.

### 6. Get build logs from failed steps

Once you know the pod name and which step failed, fetch logs:

**Live cluster:**

```bash
oc logs $POD_NAME -n $NAMESPACE -c step-build 2>&1 | tail -80
```

**KubeArchive:**

```bash
curl -sS --max-time 15 -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/api/v1/namespaces/$NS/pods/$POD_NAME/log?container=step-build" | tail -80
```

Common step container names: `step-build`, `step-prefetch-dependencies`,
`step-push`.

Show the last ~80 lines which usually contain the error. If the error
references an earlier issue (e.g., a dependency chain), fetch more lines to
capture the full context.

### 7. Cross-reference with GitHub

If this is a PR pipeline run (name contains `on-pull-req`), identify the
associated PR:

- The component name is the prefix before `-on-pull-req...` (e.g.,
  `odh-workbench-jupyter-universal-cpu-py312-ubi9`)
- Search recent PRs on the relevant repo for matching Konflux checks

```bash
gh pr list --repo opendatahub-io/notebooks --state all --limit 10 \
  --json number,title,headRefName,state
```

Then get the full checks status for the matching PR:

```bash
gh pr checks $PR_NUMBER --repo $REPO
```

This provides broader context: did GHA builds also fail? Are there other
Konflux components failing?

### 8. Report findings

Produce a summary with:

- **Status**: Succeeded / Failed / Running (with duration if available)
- **Task breakdown**: which tasks passed/failed/are running
- **Root cause** (for failures): the actual error from the build logs
- **Failure classification**:
  - `calver`/`setuptools`/dependency missing → prefetch lockfile incomplete
  - `Could not find a version that satisfies` → hermetic build missing a
    transitive dep
  - `resource quota` / `PodCreationFailed` → infrastructure issue
  - `exit status 1` in buildah → Dockerfile build error
  - Step test failures → post-build test issue
- **GitHub cross-reference**: if GHA builds passed/failed and why
- **Recommendation**: what to fix or whether to re-trigger

## Cluster access notes

- Tokens are cluster-specific — a token from prd-rh01 won't work on prod-p02
- Tokens expire frequently; if you get 401, re-run `oc login --web`
- For `open-data-hub-tenant` on prd-rh01: this is ODH upstream, the
  authoritative Konflux for opendatahub-io repos
- For `rhoai-tenant` on prod-p02: this is RHOAI downstream, authoritative
  for red-hat-data-services repos
- `rhoai-tenant` on prd-rh01: legacy duplicate — safe to ignore for merge
  decisions (but still valid for log inspection)
