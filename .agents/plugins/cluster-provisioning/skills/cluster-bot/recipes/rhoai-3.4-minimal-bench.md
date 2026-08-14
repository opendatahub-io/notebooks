# RHOAI 3.4 minimal workbench benchmark (cluster-bot)

Timed end-to-end comparison: **cluster-bot `launch 4.20 aws`** (Pass A) vs **`rosa create 4.20 8h`** (Pass B). Each pass installs RHOAI 3.4 with a workbenches-only DataScienceCluster, spawns a minimal JupyterLab Notebook, uninstalls, and deprovisions via Slack `done`.

## Artifacts

| Path | Purpose |
|------|---------|
| `fixtures/rhoai-operator-sub.yaml` | Subscription — **latest** `stable-3.x` head (no `startingCSV`) |
| `fixtures/rhoai-operator-sub-pinned.yaml` | Subscription — **pinned** CSV + `Manual` (no auto-upgrade) |
| `fixtures/operatorgroup-rhods.yaml` | OperatorGroup in `redhat-ods-operator` |
| `fixtures/dsci-default.yaml` | DSCInitialization (monitoring Removed) |
| `fixtures/dsc-minimal-workbenches.yaml` | Workbenches-only DSC |
| `fixtures/notebook-minimal.yaml` | Kubeflow Notebook `bench-minimal` |
| `../../scripts/cluster-bot-rhoai-bench.sh` | Phase orchestrator + timings |
| `../../scripts/cluster-bot-prow-watch.sh` | Prow log state machine + progress |
| `.cluster-bot-bench/<pass>/` | Gitignored kubeconfig + `timings.jsonl` + `prow_states.jsonl` |

## Prerequisites

- Slack DM to cluster-bot (`U03GSGSMF38` on `redhat.enterprise.slack.com`).
- `oc` CLI installed locally.
- OCP **4.20** (RHOAI 3.4 supported).
- Pool check: `list` before each pass.

## Isolated kubeconfig

Never use `~/.kube/config`:

```bash
export BENCH_ROOT="${REPO}/.cluster-bot-bench"
export PASS=a   # or b
export KUBECONFIG="${BENCH_ROOT}/${PASS}/kubeconfig"
mkdir -p "${BENCH_ROOT}/${PASS}"
```

## Phases and KPIs

| Phase ID | Start | End condition |
|----------|-------|---------------|
| `cluster_provision` | Slack command sent (`cluster_request` event) | Kubeconfig saved + all nodes Ready |
| `operator_install` | Subscription applied | rhods-operator CSV `Succeeded` in `redhat-ods-operator` |
| `dsc_reconcile` | DSC applied | `default-dsc` phase Ready, workbenches installed |
| `notebook_spawn` | Notebook CR applied | Notebook pod Ready |
| `workbench_api` | (notebook spawn) | HTTP 200 from Jupyter `/api` in pod |
| `uninstall` | Delete notebook + DSC/operator | No rhods CSV / DSC |
| `deprovision` | Slack `done` | Bot confirms teardown (`deprovision_ack` event) |

**Primary KPI:** wall-clock from `cluster_request` to `workbench_api` complete.

**Secondary:** per-phase durations; time from CSV Succeeded to workbench API.

## Pass commands (Slack)

**Pass A**

```
list
launch 4.20 aws
```

Wait for DM with cluster ready + kubeconfig or `oc login` line. cluster-bot replies with a **Prow log link** — use `cluster-bot-prow-watch.sh` (below) instead of long Slack sleeps.

**Pass B**

```
rosa create 4.20 8h
```

Bot rejects `24h` / `48h` (`max duration for a ROSA cluster is 8h0m0s`). Ready DM uses **`cluster-admin`** + `oc login` (often no kubeconfig attachment; console may still be unavailable).

**Deprovision (both)**

```
done
```

## Prow log watch (provision state machine)

cluster-bot launch jobs log to Prow (`release-openshift-origin-installer-launch-aws-modern`). Parse the **log link** from the Slack DM (not the dashboard spinner).

**Macro states:** `importing_release` → `acquiring_leases` → `phase_pre` → `installer_running` (`launch-ipi-install-install`) → `post_install` → `nodes_readiness` → `job_succeeded` / `job_failed`

**Expected step order** (16 steps, from `ipi-aws-pre` + `ipi-install`):

1. `launch-ipi-conf` … `launch-ipi-install-hosted-loki` (config + IAM, ~5–10 min)
2. `launch-ipi-install-install` (OpenShift installer — **~45–50 min** on `launch 4.20 aws`; was ~15–25 min in early estimates)
3. `launch-ipi-install-times-collection` → `launch-nodes-readiness` → `launch-multiarch-validate-nodes` → `launch-openshift-tests-extension-admission-crd-install`

**Deviations** recorded as `kind=deviation`: `step_failed`, `build_failure`, `cluster_failed`.

```bash
# One-shot progress (poll log tail, default 30s interval in --watch mode)
./scripts/cluster-bot-prow-watch.sh --pass a --once \
  --prow-url 'https://prow.ci.openshift.org/view/gs/test-platform-results/logs/release-openshift-origin-installer-launch-aws-modern/<id>'

# Background-friendly watch until nodes-readiness or failure
./scripts/cluster-bot-prow-watch.sh --pass a --watch --poll-interval 30 \
  --prow-job release-openshift-origin-installer-launch-aws-modern --prow-id <id>
```

Writes:

- `.cluster-bot-bench/<pass>/prow_states.jsonl` — every state transition with `elapsed_sec` from `cluster_request`
- `.cluster-bot-bench/<pass>/prow_job.env` — resolved log/view URLs
- Key events mirrored into `timings.jsonl` as `prow_*` events

Console line example:

```
progress=68% steps_done=11/16 current=launch-ipi-install-install (running) elapsed_sec=1470
```

When `launch-nodes-readiness` completes in Prow, wait for Slack **“Your cluster is ready”** (often slightly before or after Prow install step logs finish), then run `--phase provision`.

### Slack vs Prow timing (Pass A reference)

Anchor on Slack `launch` message `ts` (T0). Example from `launch 4.20 aws`:

| Δ from launch | Source | Event |
|---------------|--------|-------|
| +10s | Slack bot | “cluster is being created” + Prow link |
| +6m | Prow log | `launch-ipi-install-install` starts |
| +47m | Prow log | `launch-ipi-install-install` succeeds |
| +52m | Slack bot | “Your cluster is ready” + kubeconfig |
| +55m | script | `cluster_provision` (oc login; nodes already Ready) |

Slack gives **no mid-flight updates** between +10s and +52m — use Prow watch, not long Slack sleeps.

## RHOAI operator install (cluster-bot launch clusters)

### OLM: latest 3.4.z vs pin

**Default (`rhoai-operator-sub.yaml`):** no `startingCSV` → installs channel head once (e.g. 3.4.2).

**Pinned (`rhoai-operator-sub-pinned.yaml`):** `startingCSV` + `installPlanApproval: Manual` → stays on that CSV until you approve InstallPlans. Use for prep on a fixed z or a **deliberate** upgrade test (approve upgrade plan yourself after prep).

**Never** use `startingCSV` below channel head with `Automatic` — OLM installs old z then auto-upgrades (wasted time; not controllable).

```bash
oc get packagemanifest rhods-operator -n openshift-marketplace \
  -o jsonpath='channel head: {.status.channels[?(@.name=="stable-3.x")].currentCSV}{"\n"}'
```

### OperatorGroup must be AllNamespaces

`rhods-operator` rejects `OwnNamespace` (`targetNamespaces: [redhat-ods-operator]`). Fixture uses empty `spec: {}`.

Symptom if wrong: CSV `Failed`, reason `UnsupportedOperatorGroup`, no operator pods.

### Apply order

1. `rhoai-operator-sub.yaml` (Namespace + Subscription)
2. `operatorgroup-rhods.yaml` (empty `spec`)
3. Wait until a `rhods-operator*` CSV exists, then `oc wait csv/<name> … Succeeded` (**not** `-l` — label wait fails while CSV is still Installing)
4. `dsci-default.yaml` if not auto-created (often auto-created after CSV Succeeded)
5. `dsc-minimal-workbenches.yaml` only **after** CSV Succeeded (earlier → webhook “no endpoints”), then notebook

### OLM stuck state (not a long wait)

After CSV `Failed` or manual deletion of CSV/InstallPlan, Subscription may show `InstallPlanMissing` / `UpgradePending` with **no new InstallPlan**. Recovery:

```bash
export KUBECONFIG=.cluster-bot-bench/<pass>/kubeconfig
oc delete subscription rhods-operator -n redhat-ods-operator
oc delete csv,installplan -n redhat-ods-operator --all 2>/dev/null || true
# Use whichever Subscription fixture matches the run being recovered — rhoai-operator-sub.yaml
# (channel head) or rhoai-operator-sub-pinned.yaml (pinned CSV) — reapplying the other one
# silently switches the install mode.
oc apply -f .agents/plugins/cluster-provisioning/skills/cluster-bot/fixtures/rhoai-operator-sub.yaml
oc apply -f .agents/plugins/cluster-provisioning/skills/cluster-bot/fixtures/operatorgroup-rhods.yaml
CSV=$(oc get csv -n redhat-ods-operator -o name | grep rhods-operator | head -1)
oc wait "${CSV}" -n redhat-ods-operator \
  --for=jsonpath='{.status.phase}'=Succeeded --timeout=30m
```

Healthy CSV install: **~1–15 min**, not indefinite silence.

### Credentials

| Pass | User | API | Ready payload |
|------|------|-----|---------------|
| A `launch` | **`kubeadmin`** | `https://api.ci-<id>.aws-4.ci.openshift.org:6443` | kubeconfig attachment |
| B `rosa` | **`cluster-admin`** | `https://api.<id>.openshiftapps.com:443` | `oc login` + password; workers may appear ~1–3 min later |

### Notebook image resolution

Fixture defaults to internal-registry `s2i-minimal-notebook:3.4`. The bench script patches after apply:

| `CLUSTER_TYPE` | Image used |
|----------------|------------|
| `launch` | Imagestream tag **`2024.2`** (`quay.io/modh/…` digest) — CI lacks a usable `3.4` internal mirror |
| `rosa` | Imagestream tag **`3.4`** (`registry.redhat.io/rhoai/…` digest) |

Override with `--notebook-image REF` or `NOTEBOOK_IMAGE`. If the pod still pulls the old image after patch, delete the pod / restart the StatefulSet.
## Script workflow

```bash
REPO=/path/to/notebooks
cd "${REPO}"

# 1. After Slack launch/rosa command (prefer Slack launch ts as T0):
./scripts/cluster-bot-rhoai-bench.sh --pass a --mark-event cluster_request

# 1b. When bot posts Prow link (~10s after launch), start watch:
./scripts/cluster-bot-prow-watch.sh --pass a --watch --poll-interval 30 \
  --prow-url '<prow link from DM>'

# 2. After “Your cluster is ready” DM — save credentials or kubeconfig:
#    launch CI: USER=kubeadmin, API_URL=https://api.ci-....aws-4.ci.openshift.org:6443
#    rosa: USER=cluster-admin, API_URL=https://api....openshiftapps.com:443

# 3. Provision gate (login + nodes Ready):
./scripts/cluster-bot-rhoai-bench.sh --pass a --phase provision \
  --cluster-type launch --credentials-file .cluster-bot-bench/a/credentials.env

# 4. Install through workbench API:
./scripts/cluster-bot-rhoai-bench.sh --pass a --phase install --cluster-type launch

# 5. Uninstall:
./scripts/cluster-bot-rhoai-bench.sh --pass a --phase uninstall

# 6. After Slack done + bot ack:
./scripts/cluster-bot-rhoai-bench.sh --pass a --mark-event deprovision_ack

# 7. Summary (repeat for pass b with --cluster-type rosa):
./scripts/cluster-bot-rhoai-bench.sh --pass a --summary
./scripts/cluster-bot-rhoai-bench.sh --pass b --summary
```

Or one shot after credentials are ready:

```bash
./scripts/cluster-bot-rhoai-bench.sh --pass a --phase all \
  --cluster-type launch --credentials-file .cluster-bot-bench/a/credentials.env
```

## Comparison results (2026-08-08)

| Phase | Pass A (launch) | Pass B (rosa) | Notes |
|-------|-----------------|---------------|-------|
| cluster_provision | 3290s (~55m) | 1032s (~17m) | Slack ready ~52m vs ~13m for ROSA |
| operator_install | 9s | 19s | CSV `rhods-operator.3.4.2` |
| dsc_reconcile | 21s | 271s | ROSA slower first reconcile |
| notebook_spawn | 56s | 104s | Launch used quay.io `2024.2` fallback |
| workbench_api | 3s | 2s | In-pod `/api` probe |
| **E2E → workbench** | **~5597s (~93m)** | **~1500s (~25m)** | cluster_request → workbench_api |
| uninstall | 26s | 22s | |
| deprovision | ~5634s elapsed | ~1535s elapsed | Slack `done` ack |

Successful final-run values from `.cluster-bot-bench/{a,b}/timings.jsonl` (2026-08-08). Earlier failed attempts (wrong OperatorGroup, ImagePullBackOff, DSC-before-CSV) also appear in those logs — ignore non-`ok` / superseded phase rows when comparing.

## Risks

- **OperatorGroup `targetNamespaces`** → CSV `UnsupportedOperatorGroup`; use `spec: {}` (see above).
- **Stale Subscription** after CSV/InstallPlan delete → `InstallPlanMissing`; delete and reapply Subscription.
- **`oc wait csv -l …`** while Installing → `no matching resources found`; wait by CSV name.
- **DSC before CSV Succeeded** → mutating webhook has no endpoints; apply DSC only after operator is up.
- CI launch clusters: operand `s2i-minimal-notebook:3.4` is not mirrored to the internal registry; the bench script uses the `2024.2` quay.io imagestream tag on Pass A (`launch`). ROSA (Pass B) uses the `3.4` tag when `CLUSTER_TYPE=rosa`.
- Pull-secret may list `registry.redhat.io` on CI and still fail internal-registry tag pulls — prefer the quay fallback on launch.
- Do not use repo `make deploy9-*` — that bypasses the workbenches operator; this benchmark uses the Kubeflow `Notebook` CR.
- Channel `stable-3.x` may install CSV **3.4.2** even when `startingCSV` is **3.4.0** with `Automatic` — that triggers an immediate upgrade; use default or pinned fixtures above.
- ROSA duration max is **8h**; `rosa create … 24h` is rejected by the bot.
## References

- [RHOAI 3.4 install docs](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.4/html/installing_and_uninstalling_openshift_ai_self-managed/installing-and-deploying-openshift-ai_install)
- [cluster-bot SKILL](../SKILL.md)
