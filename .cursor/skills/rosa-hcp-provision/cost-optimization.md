# Cost optimization for ROSA HCP + RHOAI test clusters

Findings from validating `red-hat-data-services/ods-ci#3027` end-to-end on
two real ROSA HCP clusters (2026-08-08). Every number here was measured or
directly queried during that session — treat the *methods* as durable,
the *numbers* as drifting and worth re-checking. Spot instances have
their own document, [spot-instances.md](spot-instances.md) — not covered
here since they aren't usable today regardless of the other levers below.

## 1. Baseline cost — the config actually used

2× `m5.2xlarge` on-demand, 2× 300GiB gp3, single-AZ `us-east-1a`, RHOAI
2.25.9 with only `dashboard`+`workbenches` enabled:

| Line item | $/hr | How verified |
|---|---:|---|
| EC2 (2× `m5.2xlarge`) | $0.768 | Exact-SKU lookup, AWS Price List Bulk API (method below) |
| EBS (2× 300GiB gp3) | $0.068 | Same method, `productFamily=="Storage"`, `volumeApiName=="gp3"` |
| **AWS infra subtotal** | **$0.836** | |
| ROSA worker fee (16 vCPU × $0.171/4vCPU-hr) | $0.684 | [ROSA pricing page](https://aws.amazon.com/rosa/pricing/) |
| ROSA HCP control-plane fee | $0.25 | Same |
| **If ROSA fee is metered on this account** | **$1.77** | |
| **If waived (internal shared account)** | **$0.836** | |

**Method — exact-SKU pricing lookup, no IAM permission needed** (the
`pricing:GetProducts` API action and `ce:GetCostAndUsage` are both denied
on the `585132637328-rhoai-dev` role — see item 8 — so use the public,
unauthenticated AWS Price List Bulk API instead):

```bash
curl -s -o /tmp/ec2-pricing.json \
  "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.json"
# ~460MB, one-time download

# Find the exact SKU for an instance type/config
jq -r '.products | to_entries[] | select(.value.attributes.instanceType=="m5.2xlarge"
  and .value.attributes.operatingSystem=="Linux" and .value.attributes.tenancy=="Shared"
  and .value.attributes.capacitystatus=="Used") | .key' /tmp/ec2-pricing.json

# Look up that SKU's on-demand price
jq -r '.terms.OnDemand.<SKU> | to_entries[].value.priceDimensions
  | to_entries[].value | "\(.pricePerUnit.USD) USD per \(.unit)"' /tmp/ec2-pricing.json
```

Same pattern works for EBS (`productFamily=="Storage"`).

## 2. Spot instances — not usable yet, see [spot-instances.md](spot-instances.md)

Originally expected to be the top cost lever here (~50% off EC2 at the
same instance size). **It isn't usable today, on either the client or
the service side** — this turned out substantial enough (JIRA/Slack
trail, upstream design doc, interruption-notification mechanics, a
verified `rosa --debug` repro) to warrant its own document rather than
bulking up this one with content that isn't currently actionable for
provisioning. Short version: `rosa create machinepool
--use-spot-instances` is a silent no-op on `rosa` 1.2.64 (verified), the
live OCM service doesn't expose the field yet either, and there's a
service-enforced minimum OCP version (4.22) on top of that. Tracked
upstream as [`ROSA-26`](https://redhat.atlassian.net/browse/ROSA-26),
CLI ETA ~`1.2.65`/2026-08-19. Full detail, retest checklist, and the
Simple-vs-Enhanced-mode interruption-notification writeup are in
[spot-instances.md](spot-instances.md).

## 3. The requests-vs-usage distinction (critical for any sizing decision)

Idle cluster-wide **requests** were ~7.14 vCPU/19.4 GiB, while idle
**actual usage** (`oc adm top`) was ~0.4 vCPU/6.8 GiB — a >15x gap on CPU.
**The scheduler places pods based on `requests`, never on `oc adm top`.**
An earlier pass at this analysis used `oc adm top` and wrongly concluded
the cluster could shrink to a 4 vCPU/16 GiB node — it can't, on CPU alone,
without also addressing RHOAI's own request defaults (item 4).

Always compute real floors via:
```bash
oc get pods -A -o json | python3 -c '
import json, sys
def cpu(v):
    if v is None: return 0
    if v.endswith("u"): return float(v[:-1]) / 1_000_000
    if v.endswith("m"): return float(v[:-1]) / 1000
    return float(v)
def mem(v):
    if v is None: return 0
    for s,m in {"Ki":1024,"Mi":1024**2,"Gi":1024**3}.items():
        if v.endswith(s): return float(v[:-len(s)])*m
    return float(v)
def sum_requests(containers):
    tc = tm = 0
    for c in containers:
        r = c.get("resources", {}).get("requests", {})
        tc += cpu(r.get("cpu")); tm += mem(r.get("memory"))
    return tc, tm
def max_requests(containers):
    tc = tm = 0
    for c in containers:
        r = c.get("resources", {}).get("requests", {})
        tc = max(tc, cpu(r.get("cpu"))); tm = max(tm, mem(r.get("memory")))
    return tc, tm
d = json.load(sys.stdin); tc = tm = 0
for p in d["items"]:
    if p["status"].get("phase") in ("Succeeded", "Failed"): continue
    c_cpu, c_mem = sum_requests(p["spec"].get("containers", []))
    i_cpu, i_mem = max_requests(p["spec"].get("initContainers", []))
    overhead = p["spec"].get("overhead") or {}
    tc += max(c_cpu, i_cpu) + cpu(overhead.get("cpu"))
    tm += max(c_mem, i_mem) + mem(overhead.get("memory"))
print(f"{tc:.3f} vCPU, {tm/1024**3:.2f} GiB")
'
```

(This follows real Kubernetes Pod-level accounting: `max(sum(app-container requests), max(init-container request)) + overhead` per pod, and handles the `u` micro-CPU suffix alongside `m`.)

## 4. Verified: a Kyverno mutate policy CAN shrink RHOAI's own inflated requests

RHOAI's own baseline (dashboard ×2 replicas × 3 containers @ 500m/1Gi each
— `rhods-dashboard`, `oauth-proxy`, `model-registry-ui` — plus operator ×3
@ 500m) requested **5.5 of the 7.14 vCPU** at idle, far more than the
~10-220m these containers actually use. `MutatingAdmissionPolicy` (native,
CEL-based, no webhook pod) is **discoverable but disabled by default**
on this OCP 4.21 bundle — enabling it requires flipping the cluster to
`TechPreviewNoUpgrade`, an irreversible change, so don't use it for this.
**Kyverno worked instead** (already a proven pattern in this org's
`rhoai-in-kind` repo, `components/02-kyverno`):

```bash
curl -fsSL -o /tmp/kyverno-install.yaml "https://github.com/kyverno/kyverno/releases/download/v1.14.4/install.yaml"
# review it first — it creates cluster-scoped CRDs/RBAC/webhooks with your privileges
kubectl apply --server-side -f /tmp/kyverno-install.yaml
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/part-of=kyverno -n kyverno --timeout=120s
```

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: shrink-rhoai-cpu-requests
spec:
  rules:
  - name: shrink-cpu-mem-requests
    match:
      any:
      - resources:
          kinds: [Pod]
          namespaces: [redhat-ods-applications, redhat-ods-operator]  # NOT rhods-notebooks
    mutate:
      foreach:
      - list: "request.object.spec.containers"
        preconditions:
          all:
          - key: "{{ element.name }}"
            operator: AnyIn
            value: ["rhods-dashboard", "oauth-proxy", "model-registry-ui", "manager"]
        patchStrategicMerge:
          spec:
            containers:
            - name: "{{ element.name }}"
              resources:
                requests:
                  cpu: "20m"
                  memory: "256Mi"
```

The `preconditions` restricts the patch to the specific sidecar/operator
container names this doc actually measured (item 4) — without it, the
rule would mutate *any* container ever added to these two namespaces,
including future workloads that may need their real requests.

**Do not touch `rhods-notebooks`** — the notebook's own 1 CPU/8Gi request
reflects real workload need, not sidecar boilerplate; shrinking it risks
OOM-killing the actual thing being tested.

Applied, then `oc rollout restart` on `rhods-dashboard`/`rhods-operator`/
notebook-controller deployments (mutations only affect pods at admission —
existing pods don't retroactively change). Memory requests merge correctly
by key via `patchStrategicMerge` (confirmed: `memory: 1Gi` was preserved
when only `cpu` was patched in the first pass; both were patched together
in the second pass without issue).

**Measured result:**

| | Before | After Kyverno (CPU only) | After Kyverno (CPU+mem) |
|---|---:|---:|---:|
| Cluster-wide idle requests | 7.14 vCPU / 19.4 GiB | 2.26 vCPU / 19.67 GiB | **2.26 vCPU / 15.17 GiB** |
| Per-node split | 6.42 / 0.72 vCPU (skewed) | 1.30 / 0.96 vCPU (even) | 1.30 / 0.96 vCPU (even) |
| + one Small notebook (1 vCPU/8Gi) | 8.14 vCPU / 27.4 GiB | 3.26 vCPU / 27.67 GiB | **3.26 vCPU / 23.17 GiB** |

Against `m5.xlarge`×2 (~7.0 vCPU / ~29.8 GiB allocatable total): the
patched floor (3.26 vCPU / 23.17 GiB) **fits with real margin now** — CPU
comfortably (53% headroom), memory more tightly (~22% headroom
cluster-wide, but per-node margin could be thin under worst-case
bin-packing — a real notebook spawn on `m5.xlarge` with this policy
applied was not tested end-to-end this session, only computed). **Verdict:
viable with caution, not unconditionally proven** — the missing step for
full confidence is an actual notebook spawn on real `m5.xlarge` nodes with
the policy live.

## 5. "Already optimal, and why" — don't just say keep-as-is, justify it

- **Region `us-east-1`**: wins on two axes simultaneously, not a
  tradeoff — it's the cheapest-or-tied-cheapest AWS region for EC2 in
  most families, **and** quay.io (the backend behind
  `registry.redhat.io`, serving every RHOAI notebook image) has its
  origin here, fronted by CloudFront. Picking `us-east-1` means lowest
  compute price *and* shortest path to the image origin at once.
- **Single-AZ (`us-east-1a`)**: the cheapest *valid* topology, not just
  "an" option — the 2-replica HCP floor is satisfiable within one AZ, so
  spreading across AZs would only add cross-AZ data-transfer charges
  ($0.01/GB each way) for zero benefit on an ephemeral test cluster with
  no HA requirement.
- **Minimal DSC components** (`dashboard`+`workbenches` only): cheapest
  *sufficient* configuration for IDE/spawn/clone-focused tests
  specifically, not a general rule — a model-serving validation run needs
  `kserve`, etc. Re-justify per test target.
- **ROSA HCP's AWS-account footprint is minimal by architecture**:
  among the resources observed by the item 6 queries (region-scoped,
  tag- or name-filtered — not an account-wide inventory) — zero NAT
  gateways, load balancers, or Elastic IPs in the customer account for
  either cluster tested. Those live on Red Hat's side of the HCP split.
  Worker EC2 + their EBS volumes were the only cost sources *these
  specific queries* turned up — don't treat this as a verified total
  account bill without running an actual account-wide inventory/billing
  check.

## 6. Verification methodology — audit exactly what a cluster costs

```bash
AWS_REGION="${AWS_REGION:-us-east-1}"
aws ec2 describe-instances --region "$AWS_REGION" --filters "Name=tag:api.openshift.com/name,Values=<cluster>" \
  --query "Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,Lifecycle:InstanceLifecycle,State:State.Name}"
aws ec2 describe-volumes --region "$AWS_REGION" --filters "Name=tag:api.openshift.com/name,Values=<cluster>" \
  --query "Volumes[].{ID:VolumeId,Size:Size,State:State}"
aws ec2 describe-nat-gateways --region "$AWS_REGION" --filter "Name=tag:api.openshift.com/name,Values=<cluster>"
aws elbv2 describe-load-balancers --region "$AWS_REGION" --query "LoadBalancers[?contains(LoadBalancerName,'<cluster>')]"
aws ec2 describe-addresses --region "$AWS_REGION" --filters "Name=tag:api.openshift.com/name,Values=<cluster>"
```
Run this *before* deciding a cluster's cost is fully accounted for — don't
rely on memory of what was created, and pass `--region` explicitly (these
queries only cover the region you point them at). Also useful for
confirming spot lifecycle (see [spot-instances.md](spot-instances.md)) and
catching orphaned volumes (item 7).

## 7. IAM permission gap on the shared role

`585132637328-rhoai-dev` (via `rh-aws-saml-login iaps-rhods-odh-dev`) has
**neither `pricing:GetProducts` nor `ce:GetCostAndUsage`**. This means
nobody using this role can query the Pricing API directly or pull real
Cost Explorer numbers — only the public Bulk API workaround (item 1) is
available, which gives *list* prices, not actual billed amounts. If real
billed-cost verification is ever needed (e.g. confirming whether the ROSA
software fee is actually waived on this account, per item 1's open
question), request `ce:GetCostAndUsage` added to this role — this is a
fixable gap, not a permanent limitation to route around forever.

## 8. Cost-leak gotcha: orphaned EBS volumes can survive `oc delete pvc`

Found a stray unattached 20GiB gp3 volume (tagged with a `CSIVolumeName`
from an already-deleted PVC) still silently billing after a routine `oc
delete pvc --all` between test iterations. Full cluster deletion **did**
clean it up automatically this session (confirmed zero volumes remained
after `rosa delete cluster` on both test clusters) — but don't assume
that's guaranteed for volumes detached well before cluster teardown. Check
explicitly:
```bash
aws ec2 describe-volumes --region "${AWS_REGION:-us-east-1}" --filters "Name=status,Values=available" \
  "Name=tag:api.openshift.com/name,Values=<cluster>"
```

## 9. Bring-up and teardown timing — see `SKILL.md`'s "Timing" section

Full breakdown lives in `SKILL.md` near `## Prerequisites` since it's a
decision input (is a real cluster worth it?), not just a cost line item.
Two independent deletion timings this session: **14m28s** and **15m23s**
— both consistent with `deprovision.md`'s existing "~15-20 min observed"
estimate.

## 10. Alternative: `cluster-bot` for when you don't need custom sizing

The [`cluster-bot`](../cluster-bot/SKILL.md) skill's `rosa create
<version> <duration>` provisions a real ROSA HCP cluster via Slack with
**built-in auto-teardown** (`1h`/`3h`/`24h`/`48h`) — meaning there's no
risk of forgetting to delete a cluster and accruing cost indefinitely, the
exact risk this whole document is otherwise mitigating. Trade-off: **no
instance-type or disk-size control**, so the sizing/Kyverno work in this
doc doesn't apply there. Given spot instances aren't usable yet regardless
of path (see [spot-instances.md](spot-instances.md)), `cluster-bot`'s
lack of instance-type control costs less than it might first appear —
**worth defaulting to `cluster-bot` for validation runs that don't need a
specific instance type, GPU pool, or the Kyverno request-shrinking
experiment**, and reserving the manual `rosa create cluster` path in this
skill for when that control is actually needed.

## 11. RHOAI's x86_64-only image constraint is version-specific — don't assume it's permanent

True for **RHOAI 2.25** (tested here — arm64 nodes produce `exec container
process: Exec format error` on every notebook spawn). **RHOAI 3.3** already
ships arm64 variants for most (not all) component images. **RHOAI 3.6**
(upcoming) is expected to have full arm64 parity. Since Graviton (arm64)
runs ~10-20% cheaper than equivalent x86_64 on AWS, **re-test arm64
viability when validating RHOAI 3.3+** rather than inheriting this
document's 2.25-era x86_64-only conclusion — real savings are on the
table once the target RHOAI version supports it.

## 12. Verify-before-trusting checklist (the meta-lesson)

- Sizing: sum `requests` via `oc get pods -A -o json`, never eyeball `oc
  adm top`.
- Spot: see the retest checklist in
  [spot-instances.md](spot-instances.md) — don't trust `rosa create
  machinepool --use-spot-instances` exiting 0, and don't assume it's
  still unusable without re-checking (both `rosa` CLI version and the
  cluster's OCP version matter).
- Region/AZ "optimal" claims: re-derive (quick price comparison + confirm
  quay.io's origin region), don't assume they hold indefinitely.
- arm64 viability: re-test per RHOAI version, don't inherit this
  document's 2.25 conclusion.
- Cluster cost is "done": run the tag-filtered AWS queries in item 6,
  don't rely on memory of what was created.
