# 16. Route amd64 Konflux builds to in-cluster `linux/x86_64` pods (reversing the amd64 VM-pool era)

Date: 2026-08-07

## Status

Proposed

## Context

Konflux's multi-platform build pipelines take a `build-platforms` parameter per architecture leg.
For the amd64 leg, that parameter can point at either:

- **In-cluster `linux/x86_64`** — the multi-platform-controller schedules the `build-images`
  TaskRun as a normal pod (`build.appstudio.redhat.com/assigned-host: localhost`). The pod's
  `stepSpecs.computeResources` are real cgroup requests/limits: undersizing causes OOM
  (`exit 137`); the ephemeral-storage limit is a real cap that can trigger `PodEvicted`.
- **Dedicated amd64 VM machine pool** (`linux-d160-m4xlarge/amd64` and similar flavors) — the
  multi-platform-controller provisions a per-build VM and runs buildah there
  (`assigned-host: i-<instance-id>`). The same `stepSpecs.computeResources` are, in practice,
  **a no-op**: buildah is not confined to that cgroup, so a build "succeeding under 4 CPU / 8Gi"
  on a VM proves nothing about the build's actual resource use.

This repository has gone back and forth between these two choices, and this ADR records that
history so the next round-trip has the evidence in one place.

### Era 0 — in-cluster `linux/x86_64` by default (pre-Dec 2025)

Konflux's stock `multiarch-*-pipeline.yaml` templates default `build-platforms` to
`linux/x86_64`; this was also the long-standing OpenShift CI default for these images. Even at
this stage, `BuildPodEvicted: ephemeral-storage` failures on ROCm/CUDA images were already a
known, recurring problem — reported in Slack in
[Jul 2024](https://redhat-internal.slack.com/archives/C05TTTYG599/p1722350681659399) and
[Jul/Aug 2024](https://redhat-internal.slack.com/archives/C05TTTYG599/p1723213317185749)
(`#forum-ai-notebooks-server-and-extensions`), tied to
[RHOAIENG-3466](https://issues.redhat.com/browse/RHOAIENG-3466). This establishes that
ephemeral-storage exhaustion on heavy images predates Konflux and is a property of the image
sizes involved, not of any particular platform choice.

### Era 1 — move to dedicated amd64 VM machine pools

[RHAIENG-2460](https://redhat.atlassian.net/browse/RHAIENG-2460) (reported/assigned Vath Sok,
Dec 2025, Closed) states the rationale directly:

> Based on a discussion with the Konflux team, it appears that only one linux/x86\_64 is
> currently available, while linux/amd64 offers a wider range of options. Unfortunately, the
> build process on x86\_64 often results in OOM errors, preventing us from upgrading to a larger
> resource. Therefore, we should transition from linux/x86\_64 to linux/amd64 to take advantage
> of the available larger resources.

This landed via [PR #2778](https://github.com/opendatahub-io/notebooks/pull/2778)
("Update x86\_64 to amd64", merged), synced downstream via
[odh-konflux-central#95](https://github.com/opendatahub-io/odh-konflux-central/pull/95). It was
followed by several rounds of VM-flavor and `stepSpecs` tuning while still on VMs:

- [PR #2854](https://github.com/opendatahub-io/notebooks/pull/2854) — fixed a wrong platform
  flavor name that caused a Kueue `resource … unavailable` error.
- [PR #3081](https://github.com/opendatahub-io/notebooks/pull/3081) — applied a larger VM
  platform to the ROCm minimal image build.
- [PR #3160](https://github.com/opendatahub-io/notebooks/pull/3160) /
  [KONFLUX-12587](https://issues.redhat.com/browse/KONFLUX-12587) — "Update konflux resource
  stepSpecs to avoid OOM"; the author reported "no more OOMKilled" after the bump, across more
  than 20 successful builds.
- RHDS [#1751](https://github.com/red-hat-data-services/notebooks/pull/1751) /
  [#1811](https://github.com/red-hat-data-services/notebooks/pull/1811)
  ([RHAIENG-2344](https://redhat.atlassian.net/browse/RHAIENG-2344)) — bumped tensorflow to a
  larger `linux-d160-m4xlarge/arm64` VM flavor (same pattern, arm64 side).

Because `stepSpecs.computeResources` do not bind on VM builders, every one of these "fixes" was
really a VM **flavor** change (more vCPU/RAM/disk on the dedicated machine), not a resource
*request* that Kubernetes could reason about, schedule against, or enforce.

### Era 2 — reverse back to in-cluster `linux/x86_64`

[RHAIENG-6002](https://redhat.atlassian.net/browse/RHAIENG-6002) is titled "Fix Konflux build
failure: bind-mount base-images/utils directory for dnf-helper.sh" and its description is about
an unrelated buildah bug
([buildah#6631](https://github.com/containers/buildah/issues/6631)) where
`RUN --mount=type=bind` rejects a file-level source. That fix shipped separately via
[PR #4004](https://github.com/opendatahub-io/notebooks/pull/4004) (merged) and its RHDS
cherry-pick [red-hat-data-services/notebooks#2432](https://github.com/red-hat-data-services/notebooks/pull/2432).

The amd64-platform-routing and resource-sizing work described in the rest of this ADR is
**opportunistic follow-on work bundled into the same ticket/PR-branch**
(`fix/dnf-helper-directory-bind-mount`,
[PR #3994](https://github.com/opendatahub-io/notebooks/pull/3994)), not a separately chartered
decision. Readers should not assume RHAIENG-6002 itself is a platform-migration ticket.

PR #3994's commits, in order:

| Commit | Date | Summary |
|---|---|---|
| `2d415b78` | 2026-07-02 | Route ODH PR Konflux builds' amd64 leg to `linux/x86_64` |
| `3aeec900` | 2026-08-05 | Extend to push/ci-push pipelines and the multiarch default |
| `aa7753a9` | 2026-08-05 | Set `linux/x86_64` explicitly on ROCm ci-push (was relying on the default) |
| `dee382d1` | 2026-08-05 | Size `build` stepSpecs: Guaranteed 4 CPU / 8Gi + ephemeral-storage 64Gi/160Gi, now that limits actually bind |
| `08fe2d53` | 2026-08-06 | Codeserver OOM'd (`exit 137`) at 4.6/8Gi &rarr; bumped to 16 CPU / 32Gi / 160Gi |
| `9bfbe6f8` | 2026-08-06 | Peak-align: dropped most steps from "32Gi folklore" to ~8Gi Guaranteed based on live peaks; codeserver 16/32/160&rarr;8/16/80 |
| `e9a17a3d` | 2026-08-06 | tensorflow-rocm `PodEvicted` at 64Gi ephemeral &rarr; raised to 80Gi |
| `c8abe913` | 2026-08-07 | pytorch-rocm + rocm-7-14 base also `PodEvicted` at 64Gi &rarr; raised to 80Gi (same class) |

The pattern across the last five commits is consistent: switching to in-cluster pods made
resource requests real for the first time, which immediately surfaced undersized requests that
VM builders had been silently absorbing (OOM on codeserver, `PodEvicted` on two ROCm-class
images), each requiring its own follow-up commit to fix.

### Evidence on whether the reversal delivers the assumed benefit

Live monitoring during this PR's `/build-konflux` runs (recorded in
[the PR's own comment thread](https://github.com/opendatahub-io/notebooks/pull/3994#issuecomment-5215422266))
gives two results that matter for this decision:

1. **Resource control works.** On tip `c8abe9133e0c`, the full fleet went green (22/22 Konflux
   checks). Guaranteed peak-aligned sizing (8 CPU / 16Gi / 80Gi for codeserver and ROCm build
   steps) held under real load — this validates the *resource-control* rationale for pods: real
   cgroup caps that can actually be sized from observed peaks.
2. **Build speed does not reliably improve.** Among 15 multi-arch components on that tip,
   in-cluster `x86_64` finished sooner than every other architecture in only **7/15 (47%)**, and
   was measurably slower than sibling arm64 VM builds by 2-4 minutes on heavy CUDA images. A
   14-day historical sample from the prior VM-pool era showed almost the same spread (amd64-VM
   finished first in 43% of multi-arch PLRs, last in 35%) — wall-clock finish order was already
   close to a coin flip against arm64 *before* this change, and moving amd64 to pods did not
   change that outcome. It only made the resource *requests* real; it did not make the *builds*
   faster.

## Decision

Reverse the amd64 build-platform leg from dedicated VM machine pools back to in-cluster
`linux/x86_64`, across pull-request, push, and ci-push PipelineRuns, and the
`multiarch-odh-main-combined-pipeline.yaml` default. Size the `build` step (and the
resource-heavy post-build steps: `sbom-syft-generate`, `prepare-sboms`, `clair-scan`,
`ecosystem-cert-preflight-checks`) with Guaranteed-QoS `computeResources`
(`requests == limits`) and an explicit `ephemeral-storage` limit, derived from live Prometheus
peaks observed on in-cluster builds rather than from historical VM-era success (which never
exercised these limits as real caps).

We do this specifically *because* VM builders make `stepSpecs.computeResources` a no-op: only
on in-cluster pods does sizing this correctly do anything — protect against noisy-neighbor
scheduling, make quota usage predictable, and catch OOM/eviction before it happens instead of
after.

## Consequences

- **Real, enforceable, auditable resource requests.** For the first time, `build`,
  `sbom-syft-generate`, `prepare-sboms`, `clair-scan`, and `ecosystem-cert-preflight-checks`
  have `stepSpecs.computeResources` that are actually binding on the amd64 leg.
- **Caught real problems the VM era had been hiding.** Two `ephemeral-storage`-class
  `PodEvicted` failures (tensorflow-rocm, then pytorch-rocm/rocm-7-14-base) and one OOM
  (codeserver, `exit 137`) surfaced only once amd64 moved to pods, and were fixed in follow-up
  commits within the same PR.
- **Build finish time is not consistently improved.** Do not present this migration as a
  performance win: on both the new in-cluster tip and the prior VM era, amd64 finished before
  every sibling architecture only in the 43-47% range, and was routinely a few minutes behind
  arm64 VMs on the heaviest CUDA images. The benefit is resource *control*, not build *speed*.
- **Per-image sizing is now an ongoing cost.** Every image family with unusual build behavior
  (codeserver's `npm`/vscode build, ROCm's large unpacked layers) needs its own sizing pass;
  this PR alone took five follow-up commits over about 36 hours to reach a stable, peak-aligned
  set of limits. Future new images should expect the same trial-and-error unless sized from
  live peaks up front.
- **`container_fs_usage_bytes` under-reports buildah's real ephemeral-storage usage.**
  `PodEvicted`, not the Prometheus filesystem metric, remains the only reliable signal for
  ephemeral-storage sizing; this should be assumed for any future image added to the fleet.

## References

- [RHAIENG-2460](https://redhat.atlassian.net/browse/RHAIENG-2460) — original decision to move
  amd64 from `linux/x86_64` to VM machine pools, for larger resources / to avoid OOM.
- [RHAIENG-6002](https://redhat.atlassian.net/browse/RHAIENG-6002) — dnf-helper bind-mount bug
  ticket that this PR's branch grew out of; not itself a platform-migration ticket.
- [KONFLUX-12587](https://issues.redhat.com/browse/KONFLUX-12587) — VM-era `stepSpecs` OOM fix.
- [RHOAIENG-3466](https://issues.redhat.com/browse/RHOAIENG-3466) — earlier OpenShift CI
  ephemeral-storage eviction issue, cited as prior art for the same failure class.
- [buildah#6631](https://github.com/containers/buildah/issues/6631) — root cause of the
  dnf-helper bind-mount failure.
- PRs: [#2778](https://github.com/opendatahub-io/notebooks/pull/2778),
  [#2854](https://github.com/opendatahub-io/notebooks/pull/2854),
  [#3081](https://github.com/opendatahub-io/notebooks/pull/3081),
  [#3160](https://github.com/opendatahub-io/notebooks/pull/3160),
  [#3994](https://github.com/opendatahub-io/notebooks/pull/3994) (this decision) and its
  [resource/timing analysis comment](https://github.com/opendatahub-io/notebooks/pull/3994#issuecomment-5215422266).
- [`docs/konflux.md`](../../konflux.md) — operational Konflux reference; VM `host-config` and
  pipeline resource override sections should stay consistent with this ADR.
- ADR [0011](0011-abandon-pull-request-target-for-pr-builds.md) — closest existing ADR
  precedent for a CI-platform-routing decision (style/format template for this ADR).
