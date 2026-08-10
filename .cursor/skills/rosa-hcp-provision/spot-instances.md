# Spot instances on ROSA HCP — not usable yet (as of 2026-08-08)

**Bottom line up front: don't spend time on spot for ROSA HCP right now.**
It's not a bug you can work around — the feature doesn't exist yet on
either the client or the service side. This doc exists so the next
session doesn't have to re-derive that from scratch, and so the retest
conditions are obvious once the feature actually ships. See
[cost-optimization.md](cost-optimization.md) for the rest of the cost
picture (sizing, Kyverno, "already optimal" reasoning, etc.) — this file
is spot-only because the investigation ended up substantial and isn't
currently actionable for day-to-day provisioning.

## Current status: not usable, on either side

`rosa create machinepool --use-spot-instances [--spot-max-price N]` is
accepted with **no error or warning**, but the resulting machine pool has
no spot configuration at all — instances launch as regular on-demand.
Anyone trusting this flag would silently pay full price while believing
they're saving ~50%.

**This isn't a CLI-only gap — the live OCM service itself doesn't expose
the field yet either.** The `rosa-enhancements` PR #59 client-contract
design doc (merged) states this explicitly in its "Dependency and
Blocker Summary":

> The main blocker is still upstream API/model shape, not client syntax:
> current HCP API/model surfaces do not yet expose `spot_market_options`
> on `AWSNodePool`; current HCP cluster model surfaces do not yet expose
> `aws.termination_handler_queue_url`; **minimum OCP 4.22 required**
> (enforced by the service).

So even a hand-crafted `curl` request straight to the OCM API bypassing
the CLI entirely would fail server-side validation today — there's no
value in trying that until both gates below clear. (This was checked
during this investigation specifically so nobody spins up a cluster to
test it and wastes real AWS spend finding out the same thing the design
doc already says.)

**Two independent gates to clear before retesting:**

1. **`rosa` CLI ≥ 1.2.65** — see the release timeline below.
2. **Cluster OCP version ≥ 4.22** — enforced by the service, independent
   of CLI version. A cluster created on 4.21.0 (or earlier) will reject
   spot configuration even with a CLI that supports it.

## Verified repro (2026-08-08, `rosa` 1.2.64)

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
*existing* pool with `{"aws_node_pool":{"spot_market_options":{}}}` — had
no effect either (though this doesn't fully rule out "immutable after
creation" as a separate, expected restriction once the feature ships).

**Not a stale-CLI issue in the "outdated install" sense**: `rosa version`
reported `1.2.64`, matching the latest GitHub release tag at time of
testing — `brew upgrade rosa-cli` wouldn't have fixed it. It *is* a
stale-CLI issue in the "the feature hasn't shipped yet" sense.

**Action for next time**: don't assume `--use-spot-instances` worked just
because the command exited 0. Verify via:
```bash
aws ec2 describe-instances --filters "Name=tag:api.openshift.com/name,Values=<cluster>" \
  --query "Reservations[].Instances[].InstanceLifecycle"
# should print "spot" for each — if it prints nothing/null, you're on-demand
```

## The JIRA/Slack trail — this is tracked, not a bug to file upstream

[`ROSA-26`](https://redhat.atlassian.net/browse/ROSA-26) "Support and
expose Spot instances on ROSA HCP" — `In Progress`, Blocker priority,
open since 2024-05-01. Sub-epics as of 2026-08-08:

| Ticket | Summary | Status |
|---|---|---|
| `ROSAENG-61032` | ocm-api/sdk changes to support SpotMarketOptions | Closed |
| `ROSAENG-62951` | [ROSA CLI] Epic for ROSA-883 - Spot Instance Support - Preview | Closed |
| `ROSAENG-63392` | [ROSA CLI] Epic for ROSA-904 - Spot Instance simple & enhanced | **New** (created 2026-08-03) |
| `ROSAENG-60077` | [SRE] Epic — expose SpotMarketOptions through AWSNodePoolPlatform | In Progress |
| `ROSAENG-62424` | Exclude spot nodepool from `sre:nodepool:provisioning_failure_notify` | Review |

Per the release-timeline post in Slack `#wg-rosa26-aws-spot-market-options`:

> ROSA CLI: `rosa_cli_1.2.65` — target **8/19**
> Terraform provider: `tf-provider-1.7.8` — target 9/02
> Terraform HCP module: `tf-hcp-module-1.7.5` — target 9/09
> *(dates may still shift if a release cuts before then)*

We tested on `rosa` **1.2.64** — the version immediately before the one
slated to add this. That matches the observed behavior exactly: the SDK
layer already knows about `spot_market_options` (`ROSAENG-61032` closed),
but nothing in the 1.2.64 CLI populates it, and (per PR #59 above) the
live service doesn't consume it yet either. No need to file an issue
against `openshift/rosa` — `ROSA-26`/`ROSAENG-63392` already track this
exact gap.

Upstream implementation, for reference: `openshift/hypershift` PR
[#7625](https://github.com/openshift/hypershift/pull/7625) ("Add Spot
instance support in the API", **merged**) adds `marketType`
(OnDemand/Spot/CapacityBlocks) to `PlacementOptions`, a `SpotOptions`
struct (optional `maxPrice`), and `terminationHandlerQueueURL` on
`AWSPlatformSpec`. PR [#7567](https://github.com/openshift/hypershift/pull/7567)
("Spot with termination handler", **merged**) adds the actual AWS Node
Termination Handler deployment + `MachineHealthCheck` integration. Both
are merged at the HyperShift-operator level — the remaining blocker is
getting OCM/service and the ROSA CLI to actually expose and consume these
fields, plus the OCP-4.22 floor.

## Client design: Simple vs. Enhanced mode

From the `rosa-enhancements` PR #59 design doc (merged, client-facing
contract — not yet implemented in any client as of 2026-08-08):

| Mode | Queue URL | Graceful draining | Behavior |
|---|---|---|---|
| **Simple** | Not provided | **No** — `MachineHealthCheck` replaces reactively, after the node is already gone | Informational warning on Spot NodePool creation |
| **Enhanced** | Customer-provided SQS queue via `aws.termination_handler_queue_url` | **Yes** — AWS Node Termination Handler drains within the ~2-min AWS window | No extra warning |

Key details:
- **Queue URL is always optional** — Simple mode requires no support
  exception, just accept the "no graceful draining" warning.
- Enhanced mode setup is **customer-managed**, not automated by OCM: a
  standard (non-FIFO) SQS queue, AWS default attributes, tagged
  `red-hat=true`, a resource policy granting the cluster's
  `NodePoolManagement` role `sqs:DeleteMessage`/`sqs:ReceiveMessage`, and
  an EventBridge rule forwarding `EC2 Spot Instance Interruption Warning`
  + `EC2 Instance Rebalance Recommendation` events to that queue. The
  design doc calls for a future `rosa create spot-termination-queue`
  helper to automate this, but it doesn't exist yet.
- Planned CLI shape (not implemented yet): `rosa create machinepool
  --use-spot-instances --spot-max-price <N>` (unchanged from classic ROSA
  naming) plus new `rosa create/edit cluster --spot-termination-queue-url
  <url>` for Enhanced mode, upgradable day-2.
- **Spot config on an existing NodePool is mutable but disruptive** — the
  design explicitly rejects "seamless" updates; changing spot
  enablement/`max_price` triggers a recycle/replace of the underlying
  worker instances, not an in-place change.
- Planned OCM API shape (for whenever it's actually live):
  ```json
  POST /api/clusters_mgmt/v1/clusters/{cluster_id}/node_pools
  {
    "id": "spot-workers",
    "aws_node_pool": {
      "instance_type": "m5.xlarge",
      "spot_market_options": { "max_price": "0.50" }
    }
  }
  ```

## Interruption notifications — how much warning do you actually get?

**The underlying signal is plain AWS, not something ROSA extends.**
EventBridge events `EC2 Spot Instance Interruption Warning` and
`EC2 Instance Rebalance Recommendation` carry AWS's standard **~2-minute**
heads-up before reclamation — the same as any other AWS spot consumer.
ROSA HCP doesn't get more warning than that from AWS itself.

What differs by mode:
- **Simple mode (the only mode planned initially, once basic Spot support
  ships — nothing is usable today, see above)**: **zero proactive
  warning**. Nothing in-cluster
  consumes the interruption event; `MachineHealthCheck` only replaces the
  node *after* AWS has already killed it.
- **Enhanced mode (planned, not yet available)**: the AWS Node
  Termination Handler receives the interruption event via the
  customer-configured SQS queue and starts cordon+drain **within that
  same 2-minute AWS window** — it automates the *reaction*, it does not
  lengthen the window itself.

**Even Enhanced mode isn't reliable at scale.** Cited PerfScale test data
(`PERFSCALE-4503`) in the PR #59 design doc:
- All-at-once interruption of a fleet: 100% CAPI-killed (graceful) through
  ~50 nodes; around 100 nodes, results reach the 2-minute FIS boundary;
  at 200 nodes, a "substantial fraction" of instances are force-killed
  instead of gracefully drained.
- Batched interruptions: 25-node batches keep termination-handler metrics
  flat through 500 total nodes, and a 5-minute batch interval performs
  better than a 2-minute interval at 500 nodes.
- PerfScale also flagged upstream throttling at the default
  `aws-node-termination-handler` client-go `QPS=5` setting
  ([issue #1280](https://github.com/aws/aws-node-termination-handler/issues/1280)).

**Practical takeaway for planning around spot, once it ships**: budget
for exactly AWS's ~2 minutes, assume **zero automated warning** unless
you've set up Enhanced mode yourself, and don't expect graceful draining
to hold up if a large fraction of your fleet is interrupted at once even
in Enhanced mode.

## Real spot prices observed (method, not eternal truth)

For when spot does become usable — the pricing side already works via
the standard AWS API, only the ROSA HCP provisioning path is blocked:

```bash
START_TIME="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v-1H +%Y-%m-%dT%H:%M:%S)"
aws ec2 describe-spot-price-history --region us-east-1 \
  --instance-types m5.2xlarge m5.xlarge m5.large m6i.large \
  --product-descriptions "Linux/UNIX" --availability-zone us-east-1a \
  --start-time "$START_TIME"
```

Observed 2026-08-08, `us-east-1a`: `m5.2xlarge` $0.192/hr (vs. $0.384/hr
on-demand, ~50% off), `m5.xlarge` $0.065/hr, `m5.large` $0.0439/hr,
`m6i.large` $0.0384/hr. Always re-query before relying on a number — spot
prices fluctuate independently of the feature-availability question
above.

## Retest checklist

- [ ] `rosa version` ≥ `1.2.65` (check GitHub releases if the date has
      passed — the 8/19 target may have shifted)
- [ ] Cluster's OCP version ≥ 4.22 (a cluster created on an older version
      won't work even with a newer CLI — this is enforced service-side)
- [ ] Re-read `ROSA-26` and `ROSAENG-63392` for current status before
      assuming either gate has cleared
- [ ] If both gates clear: retry the `rosa --debug` repro above and
      confirm `spot_market_options` now appears in the request, then
      confirm `InstanceLifecycle` on the actual EC2 instances
- [ ] Only after that: consider whether Simple mode (no warning, no
      graceful drain) is acceptable for a throwaway test cluster, or
      whether Enhanced mode's manual SQS/EventBridge setup is worth it
      for the specific run
