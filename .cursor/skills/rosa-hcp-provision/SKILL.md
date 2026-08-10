---
name: rosa-hcp-provision
description: Provision and deprovision ROSA HCP clusters on the shared RHOAI AWS account (rh-aws-saml-login, org 7081269). Covers cluster create, G5g pools (prefer 2xlarge), GPU Operator, namespace pull-secret for quay.io/rhoai, pool resize, bring-up/teardown timing, cost optimization (cost-optimization.md — sizing, Kyverno request-shrinking; spot-instances.md — spot instance status/blockers, not usable yet), installing a released RHOAI version (install-rhoai.md), and installing an EA/pre-release RHOAI build via custom CatalogSource + Kyverno + Gateway API/Service Mesh 3 (install-prerelease.md). GPU image test procedure lives in arm64-rosa-gpu-smoke skill.
---

# ROSA HCP Cluster Provisioning

Need a quick disposable ROSA/OCP cluster with zero setup (no `kinit`/SAML) instead? See [cluster-bot](../cluster-bot/SKILL.md)'s `rosa create <version> <duration>` — has **built-in auto-teardown** (no risk of a forgotten cluster accruing cost) but no GPU pools or instance-type control. Given spot instances aren't usable yet regardless of path (not just a CLI gap — see [spot-instances.md](spot-instances.md)), `cluster-bot` is the better default when you don't specifically need a custom instance type, GPU pool, or the request-shrinking Kyverno experiment — come back here for that.

## Timing — is a real cluster worth it?

Measured end-to-end on a real ROSA HCP cluster (2026-08-08), RHOAI 2.25.9
with `dashboard`+`workbenches` only:

| Phase | Duration |
|---|---:|
| `rosa create cluster` → cluster `ready` | ~10-12 min |
| → compute nodes `Ready` | +~4-5 min |
| → all cluster operators `Available` | +~4 min |
| **Cluster fully usable** | **~19-20 min** |
| RHOAI operator Subscription → CSV `Succeeded` | ~1-2 min |
| DSCI/DSC apply → dashboard pods `Running` | ~1-2 min |
| **RHOAI (dashboard+workbenches only) install** | **~2-4 min** |
| **Combined, clean path** | **~22-24 min** |
| `rosa delete cluster` → fully gone | ~14-15 min (2 independent measurements) |

Getting the compute architecture wrong (defaulting to this skill's
GPU-oriented `m6g.2xlarge`/arm64 for a RHOAI/notebook workload — see
`## GPU Machine Pools` below and [cost-optimization.md](cost-optimization.md)
item 12) costs an *additional* ~20-25 min to swap to x86_64 after the
fact. Pass an explicit x86_64 `--compute-machine-type` up front to avoid
this entirely.

Budget **~40 min minimum** for a full create-install-delete cycle before
deciding a real cluster is the right tool versus local `kind` or
`cluster-bot`.

## Prerequisites

| Tool | Install | Purpose |
|------|---------|---------|
| `rosa` | [GitHub releases](https://github.com/openshift/rosa/releases) (keep latest!) | Cluster lifecycle |
| `aws` | `brew install awscli` | AWS credential verification |
| `rh-aws-saml-login` | `pipx install rh-aws-saml-login` | STS creds via Kerberos+SAML |
| `ocm` | `brew install ocm` | OCM org verification (optional) |
| `oc` | [mirror](https://access.redhat.com/downloads/content/290) | Cluster interaction post-create |
| `helm` | `brew install helm` | **Required for the Pre-Release Images (Kyverno) path only** — the raw `kubectl apply -f install.yaml` route hits `FailedCreate`/SCC errors on ROSA HCP (upstream manifest hardcodes `runAsUser: 65534`, outside the namespace's allowed UID range); Helm's `--set ...securityContext=null` flags (see Option A below) are the documented way around it. Without `helm`, the fallback is manually patching `runAsUser`/`runAsGroup` out of each Kyverno controller Deployment post-apply — works, but do this only if you can't install `helm`. |

Valid Kerberos ticket required: `kinit <user>@IPA.REDHAT.COM`

On macOS with credentials in Keychain: `kinit --keychain <user>@IPA.REDHAT.COM` (no password prompt).

## Critical: SAML wrapper pattern

All AWS-account-backed `rosa`/`aws` commands MUST use `--` to separate SAML wrapper flags from the wrapped command. This does not apply to the initial browser-based `rosa login --use-auth-code` (see `## Authentication` below) — that's a personal SSO step, not an AWS-account operation, and runs unwrapped.

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- <command> [flags...]
```

Without `--`, flags like `--sts` are consumed by `rh-aws-saml-login` itself (`No such option` error).

Static `~/.aws/credentials` keys are almost always stale. Never rely on them — always use the SAML wrapper.

## Critical: always pass `--context`, never rely on the ambient current-context

`~/.kube/config`'s `current-context` is global, mutable, shared-machine state —
**not scoped to this skill's session**. A real incident this happened live: mid-session,
`oc` silently started hitting a completely different cluster (a Konflux
prod cluster, `stone-prod-p02`) because *something else* on the same
machine changed `current-context` in between commands — commands
returned `Forbidden` errors that looked like a permissions problem but
were actually "wrong cluster entirely." Assume you are not the only
process touching this machine's kubeconfig, ever — a parallel agent, a
teammate's shell, or your own earlier `oc login` to a different cluster
can all silently redirect a bare `oc` invocation.

**The fix costs one extra flag per command and closes the entire failure
class:** capture the exact context name once, right after login (see
`## Post-Create Setup` below), then pass `--context "$CLUSTER_CONTEXT"`
on **every single `oc` invocation** for the rest of the session — never a
bare `oc get`/`apply`/`delete`/`patch`. Before any destructive or
mutating sequence (deleting a Subscription, patching a CatalogSource,
scaling a Deployment to 0, etc.), run a cheap verify-first check:

```bash
oc --context "$CLUSTER_CONTEXT" whoami --show-server
# MUST print https://api.<your-cluster-domain>... — if it doesn't match
# the cluster you think you're on, STOP before running anything else.
```

This mirrors the same discipline the `run-rhoai-in-kind` skill already
uses for the local kind cluster (`--context kind-kind -n <ns>`, verify
`server=127.0.0.1:6443` before mutating) — the principle is identical,
just with a dynamically-named context here instead of a fixed one.

## Authentication

### Login sequence

```bash
# 1. ROSA login (browser SSO — use account with org 7081269)
rosa login --use-auth-code
# Output: "Logged in as 'rhoai-<user>' on 'https://api.openshift.com'"

# 2. Verify ROSA identity
rh-aws-saml-login iaps-rhods-odh-dev -- rosa whoami
# MUST match:
#   OCM Organization External ID: 14351703
#   OCM Organization ID:          1pwwsfazToamNegaehP6eaDg80K
#   OCM Organization Name:        Red Hat, Inc.
#   AWS Account ID:               585132637328

# 3. Verify AWS
rh-aws-saml-login iaps-rhods-odh-dev -- aws sts get-caller-identity
# Account: 585132637328, Arn contains your username (not osdCcsAdmin)
```

### If wrong OCM org

Your personal `jdanek@redhat.com` SSO may map to a different org. The RHOAI shared org requires:
1. Open **incognito** tab at https://console.redhat.com/openshift
2. Login with account showing **Account number: 7081269** in top-right
3. `rosa logout` then `rosa login --use-auth-code` in that browser session

If you never received the 7081269 invite, request in **#rhoai-devtestops-requests** Slack.

## Cluster Creation

**`m6g.2xlarge` below is aarch64/Graviton — this is the right default for
the GPU workflow this skill was written for (pairs with G5g GPU pools,
see `## GPU Machine Pools`), but is the WRONG default for RHOAI/notebook
testing.** RHOAI 2.25's default notebook images are x86_64-only; arm64
nodes produce `exec container process: Exec format error` on every
notebook spawn (confirmed 2026-08-08, cost ~20-25 min to recover from by
swapping pools after the fact). **For RHOAI work, use an x86_64 type
(e.g. `m5.2xlarge`) here instead** — see
[cost-optimization.md](cost-optimization.md) item 12 for why this is
version-specific (RHOAI 3.3+ may not have this restriction).

```bash
export CLUSTER_NAME=<unique-name>    # MAX 15 chars! (longer triggers interactive prompt)
export MACHINE_POOL_TYPE=m6g.2xlarge # aarch64 — for GPU work. RHOAI/notebook testing: use m5.2xlarge (x86_64) instead.

# Shared infra constants
OIDC=23c734st3pn7l167mq97d0ot8848lgrl
INSTALLER=arn:aws:iam::585132637328:role/shared-rosa-hcp-HCP-ROSA-Installer-Role
SUPPORT=arn:aws:iam::585132637328:role/shared-rosa-hcp-HCP-ROSA-Support-Role
WORKER=arn:aws:iam::585132637328:role/shared-rosa-hcp-HCP-ROSA-Worker-Role

# Subnet pairs (try in order if quota issues — first pair hit full quota 2025-04)
PRIVATE=subnet-0a2ab6507448d7c17; PUBLIC=subnet-06cddec8e0a71a16f
# alt: subnet-06f0819a60ec83b06 / subnet-0f36103ff259bed5a
# alt: subnet-0866fb9d6b2c19f24 / subnet-03e2fbd47aa625cc7
# alt: subnet-0ff7c007c4ddb3a9a / subnet-002bfa1d5944b0a79

rh-aws-saml-login iaps-rhods-odh-dev -- rosa create cluster --yes --sts \
  --oidc-config-id $OIDC --cluster-name="$CLUSTER_NAME" --mode=auto --hosted-cp \
  --subnet-ids="$PRIVATE,$PUBLIC" --compute-machine-type="$MACHINE_POOL_TYPE" \
  --role-arn=$INSTALLER --support-role-arn=$SUPPORT --worker-iam-role=$WORKER \
  --version 4.21.0
```

Optional: shrink the default 300GiB worker disk (a test cluster rarely
needs that much — see [cost-optimization.md](cost-optimization.md) item
6). Add `--worker-disk-size 100GiB` to the command above — don't paste it
as a trailing line on its own, the command above already ends at
`--version 4.21.0`.

States: `waiting → validating → installing → ready` (~10 min total).

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- rosa describe cluster -c $CLUSTER_NAME | grep State
rh-aws-saml-login iaps-rhods-odh-dev -- rosa logs install -c $CLUSTER_NAME --watch
```

## Post-Create Setup

```bash
# htpasswd IdP + cluster-admin — use --from-file, not an inline --password
# (a literal password on the command line lands in shell history and is
# visible to other processes via `ps` for the command's lifetime)
HTPASSWD_FILE=$(umask 077 && mktemp)
trap 'rm -f "$HTPASSWD_FILE"' EXIT
htpasswd -c -B -b "$HTPASSWD_FILE" admin <pw>
rh-aws-saml-login iaps-rhods-odh-dev -- rosa create idp -c $CLUSTER_NAME \
  --type htpasswd --name htpasswd --from-file "$HTPASSWD_FILE"
rh-aws-saml-login iaps-rhods-odh-dev -- rosa grant user cluster-admin \
  --user admin --cluster $CLUSTER_NAME

# oc login (get API URL from describe output)
oc login -u admin https://api.<domain-prefix>.xxxx.p3.openshiftapps.com:443

# Capture the exact context name NOW, right after login, before anything
# else on this shared machine can change current-context out from under
# you. Every oc command for the rest of this session — in this skill and
# in your own shell — should pass --context "$CLUSTER_CONTEXT" explicitly
# rather than relying on the ambient current-context (see
# "## Critical: always pass --context" above for why this matters).
export CLUSTER_CONTEXT=$(oc config current-context)
oc --context "$CLUSTER_CONTEXT" whoami --show-server   # sanity check before proceeding
```

## GPU Machine Pools

### ARM64 + T4G (only ARM GPU on ROSA — per Jeff Young)

**Prefer `g5g.2xlarge` for first GPU pool** — same T4G GPU, but DTK driver compile completes reliably (~30 min). `g5g.xlarge` often hits `MemoryPressure=True` and stalls 60+ min on the same `make nv-linux.o` line (validated on `jd-arm64-ea1`, OCP 4.21.0, driver 580.82.07).

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- rosa create machinepool \
  --cluster $CLUSTER_NAME --name gpu-arm \
  --instance-type g5g.2xlarge --replicas 1 --subnet $PRIVATE --yes
```

| Instance | vCPU / RAM | GPU | SM | DTK driver compile (observed) |
|----------|------------|-----|-----|-------------------------------|
| `g5g.xlarge` | 4 / 8 GiB | 1× T4G (16 GB) | 7.5 | **60+ min stall** — node ~104% memory, DTK ~6.3 GiB, logs frozen on `make -s -j … nv-linux.o` |
| `g5g.2xlarge` | 8 / 16 GiB | 1× T4G (16 GB) | 7.5 | **~30 min to 2/2 Ready** — node ~29% memory, DTK ~1–4 GiB during compile, gcc warnings in logs |

### AWS ARM64 GPU landscape (as of Jul 2026)

Only G5g is usable on ROSA. Other ARM+GPU instances exist but are not ROSA-compatible:

| Family | CPU | GPU | SM | ROSA? | Notes |
|--------|-----|-----|-----|-------|-------|
| **G5g** | Graviton2 (aarch64) | T4G (16 GB) | 7.5 | **Yes** | Only ARM+GPU on ROSA ([AWS docs](https://aws.amazon.com/ec2/instance-types/g5g/)) |
| **P6e-GB200** | Grace (aarch64) | GB200 NVL72 (740 GB+) | 10.0 | **No** | UltraServer only, Dallas Local Zone, Capacity Blocks ([AWS blog](https://aws.amazon.com/blogs/aws/new-amazon-ec2-p6e-gb200-ultraservers-powered-by-nvidia-grace-blackwell-gpus-for-the-highest-ai-performance/)) |
| **GH200** | Grace (aarch64) | Hopper H100 | 9.0 | **No** | Not an EC2 instance type; NVIDIA DGX Cloud / bare-metal only |

G5g sizes available in `us-east-1` (verified via `aws ec2 describe-instance-types`):

| Instance | vCPU | RAM | GPUs | VRAM | $/hr |
|----------|------|-----|------|------|------|
| g5g.xlarge | 4 | 8 GB | 1× T4G | 16 GB | $0.42 |
| **g5g.2xlarge** | 8 | 16 GB | 1× T4G | 16 GB | $0.56 |
| g5g.4xlarge | 16 | 32 GB | 1× T4G | 16 GB | $0.83 |
| g5g.8xlarge | 32 | 64 GB | 1× T4G | 16 GB | $1.37 |
| g5g.16xlarge | 64 | 128 GB | 2× T4G | 32 GB | $2.74 |
| g5g.metal | 64 | 128 GB | 2× T4G | 32 GB | $2.74 |

NVIDIA GPU Operator [platform support](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/25.3.5/platform-support.html) explicitly lists "AWS EC2 G5g instances" under supported ARM platforms.

**Caveat (verified against the platform-support page directly):** GPU
Operator 25.3.4/25.3.5's own support table lists Red Hat OpenShift only
through **4.19** — this doc pins cluster creation to **4.21.0** (see
`## Cluster Creation` above), which is past NVIDIA's stated support
matrix. It demonstrably works in practice (this exact combination —
25.3.4 + driver 580.82.07 — is what's validated throughout this doc); flag
it rather than silently assume support, and if strict vendor support
matters more than the specific 4.21 features this cluster needs, use OCP
≤4.19 instead (untested here).

### Resize GPU pool (instance type is immutable)

ROSA does **not** allow changing `--instance-type` on an existing machine pool. To upsize:

1. Create a **new** pool with the desired type (use a new name, e.g. `gpu-arm2`).
2. Wait for the new node `Ready` (~3–5 min) — **node `Ready` alone is not
   enough**, the driver still needs ~30 min to compile on it (see
   [nvidia-driver-compilation.md](nvidia-driver-compilation.md)).
3. Wait for the **new pool's** driver daemonset pod to be `2/2 Ready` and
   `nvidia.com/gpu` allocatable on that specific node — scope the check to
   the new pool via its `hypershift.openshift.io/nodePool` label, not a
   generic `nvidia.com/gpu.present=true` selector that could also match
   the still-healthy *old* pool and give a false green light.
4. Only then delete the old pool — GPU Operator reschedules driver
   daemonset to the new node and recompiles.

```bash
# Create bigger pool
rh-aws-saml-login iaps-rhods-odh-dev -- rosa create machinepool \
  --cluster $CLUSTER_NAME --name gpu-arm2 \
  --instance-type g5g.2xlarge --replicas 1 --subnet $PRIVATE --yes

# Wait for node
oc --context "$CLUSTER_CONTEXT" get nodes -l node.kubernetes.io/instance-type=g5g.2xlarge -w

# Wait for the driver on the NEW pool specifically (not just any GPU node)
NEW_NODE=$(oc --context "$CLUSTER_CONTEXT" get node -l hypershift.openshift.io/nodePool=gpu-arm2 -o json)
[ "$(echo "$NEW_NODE" | jq '.items | length')" -eq 1 ] || { echo "ERROR: expected exactly one node in pool gpu-arm2" >&2; exit 1; }
NEW_NODE_NAME=$(echo "$NEW_NODE" | jq -r '.items[0].metadata.name')
oc --context "$CLUSTER_CONTEXT" wait --for=condition=Ready pod -l app.kubernetes.io/component=nvidia-driver -n nvidia-gpu-operator --field-selector spec.nodeName="$NEW_NODE_NAME" --timeout=1800s
oc --context "$CLUSTER_CONTEXT" get node "$NEW_NODE_NAME" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'  # expect 1

# Remove old pool (old node drains → SchedulingDisabled → gone)
rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete machinepool \
  --cluster $CLUSTER_NAME gpu-arm --yes
```

Helper script: [resize-gpu-pool-2xlarge.sh](resize-gpu-pool-2xlarge.sh) (`CLUSTER_NAME`, `OLD_POOL`, `NEW_POOL` overridable).

On ROSA HCP the node pool label is `hypershift.openshift.io/nodePool=<pool-name>` (not `MachineSet` in the guest cluster API).

### x86_64 GPU pools

```bash
# A100 (8 GPUs, us-east-1d AZ required — see A100 doc). $PRIVATE is the
# general cluster subnet and is NOT guaranteed to be in us-east-1d — verify
# before use, don't assume:
#   aws ec2 describe-subnets --subnet-ids "$A100_SUBNET" --query 'Subnets[0].AvailabilityZone'
A100_SUBNET="${A100_SUBNET:?set to a subnet ID verified to be in us-east-1d}"
rh-aws-saml-login iaps-rhods-odh-dev -- rosa create machinepool \
  --cluster $CLUSTER_NAME --name gpu-x86 \
  --instance-type p4d.24xlarge --replicas 1 --subnet "$A100_SUBNET"
```

### After nodes join

1. OperatorHub → **Node Feature Discovery** → install → create `NodeFeatureDiscovery` instance
2. OperatorHub → **NVIDIA GPU Operator** → install → create `ClusterPolicy` (defaults)
3. Wait for all pods in `nvidia-gpu-operator` namespace to be Running
4. Verify: `oc get nodes -l nvidia.com/gpu.present=true` and `nvidia.com/gpu` in allocatable

**CLI install (faster):**

```bash
# NFD
oc --context "$CLUSTER_CONTEXT" create ns openshift-nfd
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata: {name: openshift-nfd, namespace: openshift-nfd}
spec: {targetNamespaces: [openshift-nfd]}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata: {name: nfd, namespace: openshift-nfd}
spec: {channel: stable, name: nfd, source: redhat-operators, sourceNamespace: openshift-marketplace}
EOF
oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Succeeded csv -n openshift-nfd -l operators.coreos.com/nfd.openshift-nfd --timeout=120s
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureDiscovery
metadata: {name: nfd-instance, namespace: openshift-nfd}
spec: {operand: {servicePort: 12000}, workerConfig: {configData: ""}}
EOF

# NVIDIA GPU Operator
oc --context "$CLUSTER_CONTEXT" create ns nvidia-gpu-operator
cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata: {name: nvidia-gpu-operator, namespace: nvidia-gpu-operator}
spec: {targetNamespaces: [nvidia-gpu-operator]}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata: {name: gpu-operator-certified, namespace: nvidia-gpu-operator}
spec: {channel: v25.3, name: gpu-operator-certified, source: certified-operators, sourceNamespace: openshift-marketplace, startingCSV: gpu-operator-certified.v25.3.4, installPlanApproval: Manual}
EOF

# Approve the InstallPlan pinned to the CSV above (Manual approval prevents an
# unreviewed newer CSV in the v25.3 channel from installing silently).
# Select by exact CSV match, not output order — a namespace can have more
# than one InstallPlan and "last one" isn't necessarily "the one we pinned".
# OLM creates the InstallPlan asynchronously after the Subscription is
# applied, so poll for it rather than querying once.
CSV_NAME=gpu-operator-certified.v25.3.4
INSTALLPLAN=""
for i in $(seq 1 12); do
  INSTALLPLAN=$(oc --context "$CLUSTER_CONTEXT" get installplan -n nvidia-gpu-operator -o json | \
    jq -r --arg csv "$CSV_NAME" '.items[] | select(.spec.clusterServiceVersionNames | index($csv)) | .metadata.name')
  [ "$(echo "$INSTALLPLAN" | grep -c .)" -eq 1 ] && break
  echo "waiting for InstallPlan referencing $CSV_NAME (attempt $i/12)..." >&2
  sleep 5
done
[ "$(echo "$INSTALLPLAN" | grep -c .)" -eq 1 ] || { echo "ERROR: expected exactly one InstallPlan for $CSV_NAME, found: $INSTALLPLAN" >&2; exit 1; }
oc --context "$CLUSTER_CONTEXT" patch installplan "$INSTALLPLAN" -n nvidia-gpu-operator --type merge -p '{"spec":{"approved":true}}'
oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Succeeded csv -n nvidia-gpu-operator -l operators.coreos.com/gpu-operator-certified.nvidia-gpu-operator --timeout=180s

# ClusterPolicy — extract default from CSV alm-examples (empty spec{} is invalid in v25.3+)
# Use $CSV_NAME directly (defined above), not a grep match — grep can hit an
# older/replacing CSV on reruns. alm-examples can list more than one example;
# select the ClusterPolicy one explicitly instead of blindly taking [0].
oc --context "$CLUSTER_CONTEXT" get csv "$CSV_NAME" -n nvidia-gpu-operator \
  -ojsonpath='{.metadata.annotations.alm-examples}' | \
  jq -e '[.[] | select(.kind == "ClusterPolicy")] |
    if length == 1 then .[0] else error("expected exactly one ClusterPolicy example, got \(length)") end' | \
  oc --context "$CLUSTER_CONTEXT" apply -f -

# Wait for driver to compile (builds kernel module via Driver Toolkit)
# g5g.2xlarge: ~30 min; g5g.xlarge: often 60+ min or stall — use 1800s timeout
oc --context "$CLUSTER_CONTEXT" wait --for=condition=Ready pod -l app.kubernetes.io/component=nvidia-driver -n nvidia-gpu-operator --timeout=1800s
GPU_NODES=$(oc --context "$CLUSTER_CONTEXT" get node -l nvidia.com/gpu.present=true -o json)
[ "$(echo "$GPU_NODES" | jq '.items | length')" -gt 0 ] || { echo "ERROR: no node labeled nvidia.com/gpu.present=true" >&2; exit 1; }
echo "$GPU_NODES" | jq -r '.items[] | "\(.metadata.name) gpu=\(.status.allocatable["nvidia.com/gpu"] // "MISSING")"'
```

**Important:** On first deployment, the driver pod compiles NVIDIA kernel modules on the GPU node via Driver Toolkit. Docs say 5–10 min on large x86 nodes; **G5g aarch64 needs `g5g.2xlarge` in practice** (see [nvidia-driver-compilation.md](nvidia-driver-compilation.md)). Other GPU pods stay `Init:0/1` until driver is **2/2 Ready** — normal cascade. Success looks like: driver Running, `nvidia-cuda-validator` Completed, device-plugin/validator Running, `nvidia.com/gpu` allocatable.

For DTK vs precompiled drivers, build-once-pull workflows, and aarch64 timing notes, see [nvidia-driver-compilation.md](nvidia-driver-compilation.md).

**GPU image validation (no RHOAI install):** After GPU Operator is ready, follow [arm64-rosa-gpu-smoke](../arm64-rosa-gpu-smoke/SKILL.md) Phases 3a–3b (Pod smoke + manual notebooks). Requires namespace pull-secret for `quay.io/rhoai` — see below.

## Pre-Release Images (Pull Secret)

**Installing an already-released RHOAI version instead?** You likely don't
need any of this — see [install-rhoai.md](install-rhoai.md) for the
simpler GA OperatorHub-channel path (no Kyverno, no custom pull-secret).
The rest of this section is for pre-release builds specifically.

ROSA-hosted rewrites the global pull-secret — `quay.io/rhoai` is **not** in the default cluster secret.

### Option A — full EA/pre-release install (Kyverno + Gateway API)

**See [install-prerelease.md](install-prerelease.md)** for the full,
verified recipe: Kyverno install (SCC-compatible Helm flags), the
`OCPBUGS-23901` pull-secret workaround, the 3 ClusterPolicies (with a
correction to the source doc's over-broad `replace-image-registry`
regex), custom `CatalogSource` gotchas, and — new for RHOAI 3.3+
dashboard builds — installing Red Hat OpenShift Service Mesh 3 to provide
the Gateway API controller the dashboard now depends on.

Kyverno is also useful beyond pull-secrets — see
[cost-optimization.md](cost-optimization.md) item 5 for a mutate policy
that shrinks RHOAI's own over-requested CPU/memory on test clusters.

### Option B — Namespace secret (bare GPU Pod testing)

Sufficient for [arm64 GPU smoke](../arm64-rosa-gpu-smoke/SKILL.md) without RHOAI/Kyverno:

```bash
: "${TEST_NAMESPACE:?Set TEST_NAMESPACE to a unique, dedicated namespace — this is a shared account, don't default to a personal name}"
oc --context "$CLUSTER_CONTEXT" create ns "$TEST_NAMESPACE"   # fails loudly if it already exists — don't silently reuse another operator's namespace

# This skill does NOT read your local ~/.docker/config.json automatically —
# a skill executed by an agent that silently harvests a local registry
# credential and pushes it into a cluster Secret is a real credential-theft
# pattern, independently flagged in review. Create the pull-secret yourself:
oc --context "$CLUSTER_CONTEXT" create secret docker-registry rhoai-pull -n "$TEST_NAMESPACE" \
  --docker-server=quay.io \
  --docker-username=<your-quay-username> \
  --docker-password=<your-quay-token-or-password> \
  --docker-email=unused@example.com
# (or, if you already have a dockerconfigjson you trust from your own
# secret-manager workflow — not your default Docker CLI config —
# `oc --context "$CLUSTER_CONTEXT" create secret generic rhoai-pull -n "$TEST_NAMESPACE"
# --from-file=.dockerconfigjson=<path-you-trust> --type=kubernetes.io/dockerconfigjson`)

oc --context "$CLUSTER_CONTEXT" label namespace "$TEST_NAMESPACE" pod-security.kubernetes.io/enforce=baseline
```

Reference `imagePullSecrets: [rhoai-pull]` in GPU test Pods (see arm64 skill scripts).

## Teardown

Full procedure, timings, and troubleshooting: **[deprovision.md](deprovision.md)** (validated on `jd-arm64-ea1`, Jul 2026; deletion timing re-confirmed at 14m28s and 15m23s on two separate clusters, Aug 2026).

Considered hibernating instead of deleting to preserve cost between runs —
**not possible**: `rosa hibernate cluster`/`rosa resume cluster` both
reject HCP clusters outright (`"Hibernating a cluster is not supported for
hosted clusters"` / resume requires a `Hibernating` state that HCP clusters
can never reach). Full deletion is the only way to stop the cost; see
[cost-optimization.md](cost-optimization.md) for the actual $/hr this
represents and cheaper configurations for next time.

Quick sequence:

```bash
export CLUSTER_NAME=<name>
export OPERATOR_PREFIX=<name>-w7f2   # from rosa create / delete cluster output

kinit --keychain <user>@IPA.REDHAT.COM   # if SAML login fails

rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete cluster --cluster "$CLUSTER_NAME" --yes
# Wait until cluster drops from: rosa list clusters  (~15–20 min observed)

rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete operator-roles \
  --prefix "$OPERATOR_PREFIX" --mode auto --yes

# ⚠️ NEVER delete the OIDC provider — shared across ALL team clusters
# Do NOT run: rosa delete oidc-provider
```

Machine pools (CPU + GPU) are removed with the cluster — no separate `delete machinepool` needed for full teardown.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No such option: --sts` | Missing `--` separator between rh-aws-saml-login and rosa |
| `InvalidClientTokenId` | Stale `~/.aws/credentials`; always use SAML wrapper (not bare `aws`) |
| Name >15 chars interactive prompt | Use `--yes` flag or pick shorter name |
| Wrong OCM org (not `1pwwsfazToamNegaehP6eaDg80K`) | `rosa logout`, login incognito with account 7081269 |
| `rosa version` outdated errors | `brew upgrade rosa-cli` or download latest from GitHub |
| `export: not valid in this context` | Don't paste shell comments with special chars (e.g. `≤`) |
| `rh-aws-saml-login` not found | `pipx install rh-aws-saml-login` (needs valid `kinit` first) |
| 500 error on create | Check subnet vars: `echo $PRIVATE` — must not be empty |
| `Expected a valid value for subnet for a hosted machine pool` | `rosa create machinepool` prompts interactively when multiple subnets exist in the AZ; pass `--subnet <id>` explicitly in non-interactive/scripted shells |
| `A hosted cluster requires at least 2 replicas` | HCP hard floor on the cluster's initial pool at create time — the cluster as a whole needs ≥2 replicas. Once that's satisfied, *additional* machine pools (e.g. GPU pools above) can use `--replicas 1` fine |
| Duplicate cluster name | Cluster already exists in org; `rosa list clusters` to check |
| `--use-spot-instances` seems to have no effect | It currently doesn't — not a bug, spot isn't usable yet on ROSA HCP at all (CLI *and* service-side gaps, plus a minimum OCP 4.22 requirement). Full detail, JIRA tracking, and a retest checklist: [spot-instances.md](spot-instances.md) |
| `exec container process: Exec format error` on notebook spawn | arm64/x86_64 mismatch — RHOAI 2.25's default images are x86_64-only; recreate the cluster with an x86_64 `--compute-machine-type`, or create a replacement machine pool with x86_64 `--instance-type` (see `## Cluster Creation` above) |
| ClusterPolicy `spec{}` invalid | v25.3+ requires all fields; extract default from `csv alm-examples` |
| GPU pods Pending after ClusterPolicy | Driver compiles first; other pods cascade after driver **2/2 Ready** |
| Driver compile 60+ min, logs stuck on `make nv-linux.o` | Node `MemoryPressure=True`, DTK pod ~6+ GiB — create `g5g.2xlarge` pool, delete xlarge pool |
| `oc exec` into driver toolkit hangs | Same memory pressure on `g5g.xlarge`; check `oc adm top node` |
| `oc wait` driver Ready timeout at 600s | Normal on xlarge; extend to 1800s or upsize pool first |
| `ErrImagePull` for `quay.io/rhoai/*` | Create the `rhoai-pull` Secret in the test namespace (Option B above) |
| `oc exec` hangs locally | Use Python kubernetes client — see arm64 skill `gpu-manual-tests.py` |
| `CLIENT_NOT_FOUND` from kinit | Use `kinit --keychain user@IPA.REDHAT.COM` on macOS |
| `rh-aws-saml-login` output format | Use `--output env` for shell eval, or wrap command with `-- cmd args` |
| `delete operator-roles` prompts / `invalid mode: EOF` | Add `--mode auto --yes` — see [deprovision.md](deprovision.md) |
| Cluster gone but IAM roles remain | `rosa delete operator-roles --prefix <prefix> --mode auto --yes` |
| `oc` command returns `Forbidden`/unexpected resources that look like a permissions bug | Check `oc --context "$CLUSTER_CONTEXT" whoami --show-server` first — this is often "wrong cluster entirely" because something else on a shared machine changed kubeconfig's `current-context`, not an actual permissions problem. Always pass `--context "$CLUSTER_CONTEXT"` explicitly (see `## Critical: always pass --context` above) |

## Reference Docs (fetched via gws)

| Doc ID | Title |
|--------|-------|
| `1DQgZwj0GjCASfolFeAMXQQ1ZFRvFUp_4p1ZI_GDE42c` | HOWTO: RHOAI engineering - ROSA-hosted install guide |
| `12FoMt1_djxEkhuAsRjU40aIxnlo-0SATK-E4qihYQdQ` | Installing RHOAI pre-release on ROSA-hosted (Kyverno) |
| `1OZ7vJnUg_3ei6Unb8pyPSAuYJtWQykMWgoXd2EocslA` | ROSA-HCP A100 GPU provisioning |
| `1JQcV6yV6l62dkQ0KkinDAqwa5ld6AQk8jVAXd_fm7C4` | AAET Onboarding Session 4 - Deploying RHOAI on ROSA |

Fetch with: `gws drive files export --params '{"fileId": "<id>", "mimeType": "text/plain"}' --output /tmp/doc.txt`
