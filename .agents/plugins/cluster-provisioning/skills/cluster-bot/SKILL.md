---
name: cluster-bot
description: >-
  Provision ephemeral OpenShift and ROSA test clusters via the Slack
  cluster-bot app (ci-chat-bot) — launch/rosa create/list/done/auth commands,
  capability matrix (arm64, GPU, IBM Power/Z, machine flavor), ready-to-use
  recipes, and known limitations (no hibernate, no IBM Z, no per-cluster
  instance-type/disk control). Use when asked to launch a cluster-bot
  cluster, check cluster-bot capacity, map cluster-bot capabilities, or
  choose between cluster-bot and manual ROSA CLI provisioning.
disable-model-invocation: true
---

# cluster-bot (ci-chat-bot)

Slack app for spinning up short-lived OpenShift/ROSA clusters for manual testing. Backed by `openshift/ci-chat-bot`, driven by Prow jobs defined in `openshift/release`.

## Identity & access

- Real, live bot: Slack user `U03GSGSMF38` (`ci-chat-bot`), Enterprise Grid workspace `redhat.enterprise.slack.com`. DM it directly.
- A second, same-named bot (`UE7HH01ML`) exists on another internal workspace — it does not respond (verified: no reply after 45s). It's stale/decommissioned; ignore it.
- Human help: `#forum-ocp-crt`. Docs: [ci-chat-bot FAQ](https://github.com/openshift/ci-chat-bot/blob/master/docs/FAQ.md).
- Source of truth for what's actually supported (help text can lag): [`pkg/manager/prow.go`](https://github.com/openshift/ci-chat-bot/blob/master/pkg/manager/prow.go) (`SupportedPlatforms`, `SupportedParameters`) and [`openshift/release` workflows-config.yaml](https://github.com/openshift/release/blob/master/core-services/ci-chat-bot/workflows-config.yaml) (named workflows for `workflow-launch`/`workflow-test`).

## Quick command reference

| Command | Purpose |
|---|---|
| `help`, `help launch`, `help rosa`, `help manage`, `help test`, `help build` | Category help |
| `launch <image_or_version_or_prs> <options>` | Launch an ephemeral OCP cluster |
| `workflow-launch <name> <image_or_version_or_prs> <parameters>` | Launch via a named Prow workflow (for capabilities not in `launch`'s option list, e.g. GPU) |
| `rosa create <version> <duration>` | Real ROSA HCP cluster; duration max **8h** (e.g. `1h`/`3h`/`8h`). `24h`/`48h` are rejected |
| `rosa describe <cluster>`, `rosa lookup <version>` | ROSA cluster/version info |
| `list` | Live fleet status: your + everyone's clusters, ETA to teardown, pool caps, bot uptime |
| `done` | Terminate your cluster (only valid stop verb — `stop` is unrecognized) |
| `auth` | Get kubeconfig/credentials for your most recent cluster |
| `refresh` | Retry fetching credentials after a failure |
| `test <suite> <image_or_version_or_prs> <options>`, `test upgrade <from> <to> <options>` | Run e2e/upgrade test suites |
| `workflow-test`, `workflow-upgrade` | Same, via named workflow |
| `build <version>,<org/repo>#<pr>[,...]`, `catalog build ...` | Build release/catalog images from PRs |
| `request <resource> "<justification>"`, `revoke <resource>` | GCP workspace access (7-day, non-extendable; Hybrid Platforms org only) |
| `version` | Bot version |

## Capability matrix

| Capability | Supported? | How |
|---|---|---|
| Architecture: amd64 | ✅ default | `launch 4.19 aws` |
| Architecture: arm64 | ✅ native | `launch 4.19 gcp,arm64` |
| Architecture: multi | ✅ native | `launch 4.19,<pr> aws,multi` |
| Architecture: s390x (IBM Z) | ❌ | Not in `SupportedPlatforms`/arch list at all |
| Platform: aws/gcp/azure/vsphere/metal | ✅ native | `launch 4.19 <platform>` |
| Platform: alibaba/nutanix/openstack/ovirt/azure-stackhub | ✅ native | `launch 4.19 <platform>` |
| Platform: hypershift-hosted (default) | ✅ native | `launch 4.19` |
| IBM Power (PowerVS) | ✅ native | `launch 4.19 hypershift-hosted-powervs` |
| IBM Cloud (plain VSI/IPI) | ⚠️ workflow-only, undocumented | `workflow-launch cucushift-installer-rehearse-ibmcloud-ipi 4.19` or `workflow-launch openshift-qe-installer-ibmcloud-ipi-ovn 4.19` |
| GPU nodes | ⚠️ one named workflow, AWS only | `workflow-launch openshift-psap-e2e-aws-gpu 4.19` (no GPU workflow for gcp/azure/vsphere as of writing) |
| OpenShift version (nightly/ci/X.Y/build/PR) | ✅ | See Recipes |
| Machine flavor / instance type | ❌ | No such parameter anywhere; only qualitative `size` (`compact`, `single-node`, `large`, `xlarge`, `multi-zone`) |
| Disk size | ❌ | Not exposed by any command |
| Hibernate / pause / resume | ❌ | Only `done` (full terminate) exists; `stop` → "unrecognized command" |

## Recipes

**RHOAI 3.4 minimal workbench benchmark (timed launch vs rosa):**
See [recipes/rhoai-3.4-minimal-bench.md](recipes/rhoai-3.4-minimal-bench.md), `scripts/cluster-bot-rhoai-bench.sh`, and `scripts/cluster-bot-prow-watch.sh` (Prow log state machine during provision).

**Quick amd64 AWS cluster, latest 4.19 nightly:**
```text
launch 4.19 aws
```

**ARM64 on GCP:**
```text
launch 4.19 gcp,arm64
```

**GPU cluster (AWS only):**
```text
workflow-launch openshift-psap-e2e-aws-gpu 4.19
```

**IBM Power via PowerVS:**
```text
launch 4.19 hypershift-hosted-powervs
```

**Build from one or more PRs, then launch it:**
```text
build 4.19,openshift/installer#123
launch 4.19,openshift/installer#123 aws
```

**Real ROSA HCP cluster with auto-teardown (max 8h):**
```text
rosa create 4.19 3h
# or: rosa create 4.20 8h
```

**Custom node count via a named workflow (params need double quotes):**
```text
workflow-launch hypershift-hostedcluster-workflow 4.19 "HYPERSHIFT_NODE_COUNT=4"
```

**Check current capacity before launching:**
```text
list
```
Read the header line (e.g. `20/80 clusters up`, `26/30 ROSA Clusters up`) for pool caps and current usage. If a pool shows 0 active, it's wide open.

**Get creds / clean up:**
```text
auth
done
```

## Provisioning timing and progress (learned from RHOAI bench)

### What is normal wall-clock?

| Path | Typical total to “ready” | Long pole | Bench (2026-08-08) |
|------|------------------------|-----------|--------------------|
| `launch 4.20 aws` | **~30–55 min** | Prow `launch-ipi-install-install` (~45–50 min on AWS CI) | **~55 min** provision; **~93 min** E2E → workbench `/api` |
| `rosa create 4.20 8h` | **~15–20 min** | ROSA HCP + worker Ready | **~17 min** provision; **~25 min** E2E → workbench `/api` (~3.7× faster) |

**Not normal:** sitting with no Prow movement for 20+ min after `being created`. No Slack update for 20+ min while Prow shows `ipi-install-install` still running **is** expected — use Prow, not Slack polling sleeps.

### Slack is coarse; Prow is fine-grained

| Signal | Granularity | Use for |
|--------|-------------|---------|
| Slack DM | ~2 bot messages for launch (`being created` ~+10s, `ready` ~+50m); ROSA may add “Created cluster `…`” then ready ~+13m | T0 (`launch`/`rosa create` message `ts`), credentials when ready |
| Prow build log | Step every ~8s–2m; installer step duration | Live progress, deviation detection |
| `cluster-bot-prow-watch.sh` | Poll log every **30s** | State machine + `prow_states.jsonl` |

**Anchor T0** on the Slack **`launch` / `rosa create`** message timestamp (or set `bench_start_epoch` from it). Script `cluster_request` marks can be a few seconds earlier.

**Start Prow watch** when the bot posts “cluster is being created” (~10s after `launch`) — do not wait 15–20 minutes between Slack polls.

Log API (not the dashboard spinner):

```text
https://prow.ci.openshift.org/log?job=release-openshift-origin-installer-launch-aws-modern&id=<id>
```

Parse job/id from the Slack Prow link in the DM.

### Credentials differ by cluster type

| Source | User | API host pattern | Ready DM |
|--------|------|------------------|----------|
| `launch … aws` (CI) | **`kubeadmin`** | `https://api.ci-<hash>.aws-4.ci.openshift.org:6443` | kubeconfig attachment (`cluster-bot-*.kubeconfig`) + console URL |
| `rosa create …` | **`cluster-admin`** | `https://api.<id>.openshiftapps.com:443` | `oc login` line + password; console may lag (“not currently available” — use `auth` / login anyway) |

Save to isolated `KUBECONFIG` under `.cluster-bot-bench/<pass>/` — never `~/.kube/config`. ROSA may have **0 workers** for a few minutes after the ready DM; `--phase provision` polls until nodes are Ready.

### Installing RHOAI on cluster-bot clusters

Validated on **`launch 4.20 aws`** (Pass A) and **`rosa create 4.20 8h`** (Pass B). Fixtures: `.agents/plugins/cluster-provisioning/skills/cluster-bot/fixtures/`, orchestrator: `scripts/cluster-bot-rhoai-bench.sh`.

**OperatorGroup (critical):** `rhods-operator` does **not** support `OwnNamespace` install mode. Use **AllNamespaces**:

```yaml
# fixtures/operatorgroup-rhods.yaml — correct
spec: {}
```

**Wrong** (CSV fails `UnsupportedOperatorGroup`):

```yaml
spec:
  targetNamespaces:
    - redhat-ods-operator
```

**Apply order:** namespace + Subscription first, then OperatorGroup (script does this). OperatorGroup before namespace exists → apply error; wrong OperatorGroup → CSV `Failed` with no operator pods.

**Wait for CSV by name, not label.** `oc wait csv -l operators.coreos.com/rhods-operator…` can fail with `no matching resources found` while the CSV is still `Installing` (label not present yet). Poll until a `rhods-operator*` CSV exists, then:

```bash
oc wait csv/rhods-operator.3.4.2 -n redhat-ods-operator \
  --for=jsonpath='{.status.phase}'=Succeeded --timeout=30m
```

(Bench script discovers the CSV name automatically; set `OPERATOR_CSV=…` only to pin the wait target.)

**Do not apply DSC until CSV is Succeeded.** Applying earlier hits webhook errors (`rhods-operator-service` has no endpoints).

**OLM recovery** after fixing OperatorGroup or deleting failed CSV/InstallPlan:

```bash
export KUBECONFIG=.cluster-bot-bench/a/kubeconfig
oc delete subscription rhods-operator -n redhat-ods-operator
oc delete csv,installplan -n redhat-ods-operator --all 2>/dev/null || true
# Use whichever Subscription fixture matches the run being recovered — rhoai-operator-sub.yaml
# (channel head) or rhoai-operator-sub-pinned.yaml (pinned CSV) — reapplying the other one
# silently switches the install mode.
oc apply -f .agents/plugins/cluster-provisioning/skills/cluster-bot/fixtures/rhoai-operator-sub.yaml
oc apply -f .agents/plugins/cluster-provisioning/skills/cluster-bot/fixtures/operatorgroup-rhods.yaml
# Wait until CSV appears, then wait by name (not -l):
oc get csv -n redhat-ods-operator -o name | grep rhods-operator
oc wait csv/rhods-operator.3.4.2 -n redhat-ods-operator \
  --for=jsonpath='{.status.phase}'=Succeeded --timeout=30m
```

If Subscription shows `InstallPlanMissing` / `UpgradePending` with no CSV — it is **stuck**, not slow. Delete and reapply Subscription (above).

### OLM Subscription: latest 3.4.z vs pin (do not mix accidentally)

Channel `stable-3.x` has a **head** CSV (e.g. `rhods-operator.3.4.2`). Two intentional modes:

| Goal | Fixture | `startingCSV` | `installPlanApproval` | Behavior |
|------|---------|---------------|----------------------|----------|
| **Latest 3.4.z** (default bench) | `rhoai-operator-sub.yaml` | **omit** | `Automatic` | One install at channel head — no upgrade churn |
| **Pin exact CSV** (prep/tests on fixed z) | `rhoai-operator-sub-pinned.yaml` | e.g. `rhods-operator.3.4.0` | **`Manual`** | Stays on pinned CSV until you approve an InstallPlan |

**Anti-pattern:** `startingCSV: rhods-operator.3.4.0` + `installPlanApproval: Automatic` on a channel whose head is **3.4.2**. OLM installs 3.4.0, then **immediately** plans upgrade to 3.4.2 — double install time, wrong for benchmarks, and wrong for “prepare on 3.4.0” (upgrade runs before you are ready). Not a substitute for a deliberate upgrade test either.

Check channel head before install:

```bash
oc get packagemanifest rhods-operator -n openshift-marketplace \
  -o jsonpath='{.status.channels[?(@.name=="stable-3.x")].currentCSV}{"\n"}'
```

Approve pinned install/upgrade when using Manual:

```bash
oc get installplan -n redhat-ods-operator
oc patch installplan <name> -n redhat-ods-operator --type merge -p '{"spec":{"approved":true}}'
```

Bench script waits on the discovered rhods CSV **by name** (set `OPERATOR_CSV=rhods-operator.3.4.0` only when using the pinned fixture).

**Expected RHOAI phases (healthy cluster; bench observations):**

| Phase | Typical | Notes |
|-------|---------|-------|
| CSV Succeeded | ~1–15 min after correct OperatorGroup + Subscription | Can be very fast once InstallPlan is approved |
| DSC Ready (workbenches only) | ~1–5 min (launch); ~5 min (ROSA bench) | Wait for CSV first |
| Notebook pod + Jupyter `/api` | ~1–3 min | Launch CI needs quay fallback (below) |

**Notebook image on CI `launch` clusters:** imagestream tag `3.4` points at `registry.redhat.io/…` and is **not** mirrored into the internal registry; pulls via `image-registry…/s2i-minimal-notebook:3.4` fail with auth / ImagePullBackOff even when the cluster pull-secret has a `registry.redhat.io` entry. Bench script patches the Notebook to the imagestream’s **`2024.2` quay.io digest** when `CLUSTER_TYPE=launch`. ROSA (`CLUSTER_TYPE=rosa`) uses the `3.4` digest successfully. After patching image, restart the Notebook StatefulSet if the pod still pulls the old ref.

Full bench recipe + filled comparison table: [recipes/rhoai-3.4-minimal-bench.md](recipes/rhoai-3.4-minimal-bench.md).

## Known limitations

- No hibernate/pause/resume — only immediate full teardown via `done`.
- No per-cluster instance-type or disk-size control on any command.
- IBM Z (s390x) is not supported on any platform.
- GPU is one AWS-only named workflow, not a generic flag; other clouds have none.
- IBM Cloud plain-VSI clusters only reachable via two undocumented QE `workflow-launch` names, not the standard `launch` platform list.
- GCP workspace access (`request`/`revoke`) is capped at 7 days, non-extendable, and gated to the Hybrid Platforms org.
- Fleet-wide caps exist per pool (`list` shows the denominator) — you can be capacity-blocked even if your own request is valid.
- Undocumented/mistyped commands just say "msg me `help`" — no fuzzy help; check `pkg/manager/prow.go` or `workflows-config.yaml` directly for anything not in the six `help` categories.
- `rosa create <version> <duration>` has no architecture/platform parameter at all — confirmed via `pkg/manager/rosa.go` (no arch handling anywhere in the file) and a live run: always amd64. Arch selection (`arm64`, `multi`) only exists on the `launch` (classic Prow) path.

## cluster-bot vs manual ROSA CLI

Use **cluster-bot's `rosa create <version> <duration>`** for quick, disposable ROSA HCP clusters with automatic teardown and zero local tooling — no `kinit`/SAML dance, no shared subnet/role bookkeeping. Best for short manual checks. Duration is capped at **8h**.

Use the **manual `rosa` CLI flow** (see [rosa-hcp-provision](../rosa-hcp-provision/SKILL.md)) when you need: GPU machine pools (T4G/A100/etc.), custom machine pool instance types, longer-lived clusters without a hard teardown timer, or fine control over subnets/roles/OIDC in the shared RHOAI AWS account. cluster-bot cannot do any of these — no instance-type control, no GPU pools, and `rosa create`'s duration is a hard auto-teardown (≤8h), not indefinite.
