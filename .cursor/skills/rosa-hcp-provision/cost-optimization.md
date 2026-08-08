# Cost optimization for ROSA HCP + RHOAI test clusters

Findings from validating `red-hat-data-services/ods-ci#3027` end-to-end on
two real ROSA HCP clusters (2026-08-08). Every number here was measured or
directly queried during that session — treat the *methods* as durable,
the *numbers* (spot prices especially) as drifting and worth re-checking.

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

## 2. Real spot prices observed (method, not eternal truth)

```bash
aws ec2 describe-spot-price-history --region us-east-1 \
  --instance-types m5.2xlarge m5.xlarge m5.large m6i.large \
  --product-descriptions "Linux/UNIX" --availability-zone us-east-1a \
  --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%S)"
```

Observed 2026-08-08, `us-east-1a`: `m5.2xlarge` $0.192/hr, `m5.xlarge`
$0.065/hr, `m5.large` $0.0439/hr, `m6i.large` $0.0384/hr. Always re-query
before relying on a number — spot prices fluctuate.

## 3. Spot instances DO NOT currently work via `rosa create machinepool` — verified, reproducible

**This is the single most important finding in this document.** `rosa
create machinepool --use-spot-instances [--spot-max-price N]` is accepted
with **no error or warning**, but the resulting machine pool has no spot
configuration at all — the instances launch as regular on-demand. Anyone
trusting this flag would silently pay full price while believing they're
saving ~50%.

**Verified 3 times** with `rosa --debug`, inspecting the actual HTTP
request body sent to the OCM API — `spot_market_options` (or any
spot-related field) is **absent from the request** regardless of whether
`--spot-max-price` is also passed:

```json
{
  "kind": "NodePool",
  "id": "workers-spot3",
  "aws_node_pool": {
    "kind": "AWSNodePool",
    "ec2_metadata_http_tokens": "optional",
    "instance_type": "m5.2xlarge"
  },
  "auto_repair": true,
  "labels": {},
  "replicas": 2,
  "subnet": "subnet-...",
  "taints": []
}
```

No `spot_market_options` key anywhere. Also tried a raw `ocm patch` to an
*existing* pool with `{"aws_node_pool":{"spot_market_options":{}}}` —
had no effect either (though this doesn't fully rule out "immutable after
creation" as a separate, expected restriction).

**Not a stale-CLI issue**: `rosa version` reported `1.2.64`, which matches
the latest GitHub release tag (`v1.2.64`) at time of testing — this is
current, not something `brew upgrade rosa-cli` fixes today.

**Action for next time**: don't assume `--use-spot-instances` worked just
because the command exited 0. Verify via:
```bash
aws ec2 describe-instances --filters "Name=tag:api.openshift.com/name,Values=<cluster>" \
  --query "Reservations[].Instances[].InstanceLifecycle"
# should print "spot" for each — if it prints nothing/null, you're on-demand
```
Re-test this after any `rosa` CLI upgrade; file an issue against
`openshift/rosa` if it's still broken and none exists yet.

## 4. The requests-vs-usage distinction (critical for any sizing decision)

Idle cluster-wide **requests** were ~7.14 vCPU/19.4 GiB, while idle
**actual usage** (`oc adm top`) was ~0.4 vCPU/6.8 GiB — a >15x gap on CPU.
**The scheduler places pods based on `requests`, never on `oc adm top`.**
An earlier pass at this analysis used `oc adm top` and wrongly concluded
the cluster could shrink to a 4 vCPU/16 GiB node — it can't, on CPU alone,
without also addressing RHOAI's own request defaults (item 5).

Always compute real floors via:
```bash
oc get pods -A -o json | python3 -c '
import json, sys
from collections import defaultdict
def cpu(v): return 0 if v is None else float(v[:-1])/1000 if v.endswith("m") else float(v)
def mem(v):
    if v is None: return 0
    for s,m in {"Ki":1024,"Mi":1024**2,"Gi":1024**3}.items():
        if v.endswith(s): return float(v[:-len(s)])*m
    return float(v)
d = json.load(sys.stdin); tc=tm=0
for p in d["items"]:
    if p["status"].get("phase") in ("Succeeded","Failed"): continue
    for c in p["spec"].get("containers",[]):
        r = c.get("resources",{}).get("requests",{})
        tc += cpu(r.get("cpu")); tm += mem(r.get("memory"))
print(f"{tc:.3f} vCPU, {tm/1024**3:.2f} GiB")
'
```

## 5. Verified: a Kyverno mutate policy CAN shrink RHOAI's own inflated requests

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
kubectl apply --server-side -k "https://github.com/kyverno/kyverno/releases/download/v1.14.4/install.yaml"
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
        patchStrategicMerge:
          spec:
            containers:
            - name: "{{ element.name }}"
              resources:
                requests:
                  cpu: "20m"
                  memory: "256Mi"
```

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

## 6. "Already optimal, and why" — don't just say keep-as-is, justify it

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
  verified via tag-filtered queries (item 7) — zero NAT gateways, load
  balancers, or Elastic IPs in the customer account for either cluster
  tested. Those live on Red Hat's side of the HCP split. The entire
  customer-account bill is worker EC2 + their EBS volumes, nothing else.

## 7. Verification methodology — audit exactly what a cluster costs

```bash
aws ec2 describe-instances --filters "Name=tag:api.openshift.com/name,Values=<cluster>" \
  --query "Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,Lifecycle:InstanceLifecycle,State:State.Name}"
aws ec2 describe-volumes --filters "Name=tag:api.openshift.com/name,Values=<cluster>" \
  --query "Volumes[].{ID:VolumeId,Size:Size,State:State}"
aws ec2 describe-nat-gateways --filter "Name=tag:api.openshift.com/name,Values=<cluster>"
aws elbv2 describe-load-balancers --query "LoadBalancers[?contains(LoadBalancerName,'<cluster>')]"
aws ec2 describe-addresses --filters "Name=tag:api.openshift.com/name,Values=<cluster>"
```
Run this *before* deciding a cluster's cost is fully accounted for — don't
rely on memory of what was created. Also useful for confirming spot
lifecycle (item 3) and catching orphaned volumes (item 9).

## 8. IAM permission gap on the shared role

`585132637328-rhoai-dev` (via `rh-aws-saml-login iaps-rhods-odh-dev`) has
**neither `pricing:GetProducts` nor `ce:GetCostAndUsage`**. This means
nobody using this role can query the Pricing API directly or pull real
Cost Explorer numbers — only the public Bulk API workaround (item 1) is
available, which gives *list* prices, not actual billed amounts. If real
billed-cost verification is ever needed (e.g. confirming whether the ROSA
software fee is actually waived on this account, per item 1's open
question), request `ce:GetCostAndUsage` added to this role — this is a
fixable gap, not a permanent limitation to route around forever.

## 9. Cost-leak gotcha: orphaned EBS volumes can survive `oc delete pvc`

Found a stray unattached 20GiB gp3 volume (tagged with a `CSIVolumeName`
from an already-deleted PVC) still silently billing after a routine `oc
delete pvc --all` between test iterations. Full cluster deletion **did**
clean it up automatically this session (confirmed zero volumes remained
after `rosa delete cluster` on both test clusters) — but don't assume
that's guaranteed for volumes detached well before cluster teardown. Check
explicitly:
```bash
aws ec2 describe-volumes --filters "Name=status,Values=available" \
  "Name=tag:api.openshift.com/name,Values=<cluster>"
```

## 10. Bring-up and teardown timing — see `SKILL.md`'s "Timing" section

Full breakdown lives in `SKILL.md` near `## Prerequisites` since it's a
decision input (is a real cluster worth it?), not just a cost line item.
Two independent deletion timings this session: **14m28s** and **15m23s**
— both consistent with `deprovision.md`'s existing "~15-20 min observed"
estimate.

## 11. Alternative: `cluster-bot` for when you don't need custom sizing

The [`cluster-bot`](../cluster-bot/SKILL.md) skill's `rosa create
<version> <duration>` provisions a real ROSA HCP cluster via Slack with
**built-in auto-teardown** (`1h`/`3h`/`24h`/`48h`) — meaning there's no
risk of forgetting to delete a cluster and accruing cost indefinitely, the
exact risk this whole document is otherwise mitigating. Trade-off: **no
instance-type or disk-size control**, so the sizing/Kyverno work in this
doc doesn't apply there. Given spot instances turned out not to work via
the manual CLI path anyway (item 3), `cluster-bot`'s lack of instance-type
control costs less than it might first appear — **worth defaulting to
`cluster-bot` for validation runs that don't need a specific instance
type, GPU pool, or the Kyverno request-shrinking experiment**, and
reserving the manual `rosa create cluster` path in this skill for when
that control is actually needed.

## 12. RHOAI's x86_64-only image constraint is version-specific — don't assume it's permanent

True for **RHOAI 2.25** (tested here — arm64 nodes produce `exec container
process: Exec format error` on every notebook spawn). **RHOAI 3.3** already
ships arm64 variants for most (not all) component images. **RHOAI 3.6**
(upcoming) is expected to have full arm64 parity. Since Graviton (arm64)
runs ~10-20% cheaper than equivalent x86_64 on AWS, **re-test arm64
viability when validating RHOAI 3.3+** rather than inheriting this
document's 2.25-era x86_64-only conclusion — real savings are on the
table once the target RHOAI version supports it.

## 13. Verify-before-trusting checklist (the meta-lesson)

- Sizing: sum `requests` via `oc get pods -A -o json`, never eyeball `oc
  adm top`.
- Spot: check `InstanceLifecycle` on actual EC2 instances, never trust
  `rosa create machinepool --use-spot-instances` exiting 0.
- Region/AZ "optimal" claims: re-derive (quick price comparison + confirm
  quay.io's origin region), don't assume they hold indefinitely.
- arm64 viability: re-test per RHOAI version, don't inherit this
  document's 2.25 conclusion.
- Cluster cost is "done": run the tag-filtered AWS queries in item 7,
  don't rely on memory of what was created.
