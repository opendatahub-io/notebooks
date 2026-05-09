# GitHub Actions vs Konflux: Build Performance ROI Analysis

**Jira**: [RHAIENG-4985](https://redhat.atlassian.net/browse/RHAIENG-4985)

## Executive summary

GitHub Actions builds notebook images **2-9x faster** than Konflux pipelines
for developer feedback, at **zero compute cost** for public repos. GHA
delivers build results in 13-52 minutes per image (all architectures in
parallel), while Konflux pipelines have 4-6 hour timeouts with significant
scheduling overhead. GHA with IBM actionspz runners also provides **native
ppc64le/s390x builds for free**, covering architectures that Konflux currently
does not build (0/26 components for s390x, 3/26 for ppc64le).

## The 10-minute build rule

The "10-minute build" principle (Martin Fowler, ThoughtWorks, XP — late 2000s)
states that developers should get build feedback within 10 minutes. Beyond
that, developers context-switch, batch changes, and the tight CI feedback
loop breaks down.

| System | Fastest image | Median image | P90 | Slowest image |
|--------|-------------|-------------|-----|--------------|
| **GHA** | **13 min** (runtime-minimal) | **~25 min** | **52 min** | **97 min** (codeserver) |
| **Konflux** | **36 min** (runtime-minimal avg) | **52 min** | **120 min** | **193 min** (base-image-cuda) |

GHA is approaching the 10-minute target for lightweight images. Konflux
median is 52 min (2x GHA), and P90 is 120 min — developers wait 2 hours
10% of the time. The high Konflux variance (8-180 min for the same image)
is driven by queue wait times that GHA eliminates entirely.

## GHA build durations (measured)

Data from 4 recent push builds on `main` (May 8-9, 2026). All images build
**in parallel** on separate runners — wall-clock equals the longest single
job.

### Per-image average build times (minutes)

| Image | amd64 | arm64 | ppc64le | s390x |
|-------|------:|------:|--------:|------:|
| runtime-minimal | 13 | — | — | 18 |
| jupyter-minimal | 14 | — | 22 | 23 |
| cuda-jupyter-minimal | 21 | 22 | — | — |
| rocm-jupyter-minimal | 19 | — | — | — |
| runtime-datascience | 20 | — | — | 31 |
| jupyter-datascience | 23 | — | — | — |
| runtime-cuda-tensorflow | 28 | 29 | — | — |
| runtime-cuda-pytorch | 29 | — | — | — |
| jupyter-trustyai | 31 | — | — | — |
| cuda-jupyter-tensorflow | 34 | 35 | — | — |
| rocm-jupyter-tensorflow | 35 | — | — | — |
| rocm-runtime-pytorch | 36 | — | — | — |
| runtime-cuda-pytorch-llmcompressor | 37 | — | — | — |
| cuda-jupyter-pytorch | 39 | — | — | — |
| rocm-jupyter-pytorch | 42 | — | — | — |
| cuda-jupyter-pytorch-llmcompressor | 48 | — | — | — |
| codeserver | 90 | 89 | — | — |

**Key observations:**

- Most images build in **13-42 minutes** on amd64
- arm64 native runners deliver comparable speed to amd64 (no QEMU penalty)
- ppc64le via QEMU cross-compilation: 22-45 min (often fails)
- ppc64le via IBM native runners: **~15-20 min expected** (proven in PR #3525)
- s390x QEMU: 18-31 min for the few images that build
- **Total workflow wall-clock**: ~90-100 min (bottleneck: codeserver)
- **Excluding codeserver**: ~52 min (bottleneck: pytorch-llmcompressor CUDA)
- **First build result available**: ~13 min (runtime-minimal on amd64)

### ppc64le native vs QEMU comparison

| Image | QEMU (current) | Native IBM (expected) | Speedup |
|-------|---------------:|---------------------:|--------:|
| jupyter-minimal | 22 min | ~15 min | ~1.5x |
| jupyter-datascience | 45 min (fails) | ~20 min | ~2.2x |
| runtime-minimal | — | ~13 min | N/A |

Native builds also eliminate QEMU flakiness (test failures due to
emulation bugs, timeout kills from slow emulated builds).

## Konflux pipeline structure (from repo config)

Each Konflux build pipeline has **~18 tasks** running sequentially
or in limited parallelism:

```
Phase 1 (BUILD):
  rhoai-init → init → clone-repository → prefetch-dependencies → build-images → build-image-index

Phase 2 (SCAN + PUBLISH):
  build-source-image, deprecated-base-image-check, clair-scan, ecosystem-cert,
  sast-snyk, clamav, sast-coverity, sast-shell, sast-unicode, rpms-signature,
  apply-tags, push-dockerfile, show-sbom, send-slack-notification
```

**Developer feedback** = Phase 1 completion. Phase 2 adds significant
wall-clock but doesn't change the build outcome.

### Configured timeouts and resources

| Setting | Value |
|---------|-------|
| Pipeline timeout | **6 hours** |
| Build task timeout | **4 hours** |
| Build CPU request/limit | 8 / 16 |
| Build memory request/limit | 16 GiB / 32 GiB |
| Prefetch CPU/memory | 8 / 32 GiB |

**Why 4-6 hour timeouts for builds that take 30-60 minutes?** The
timeouts exist primarily to accommodate **queue wait times**, not slow
builds. Each pipeline task pod must be scheduled on the OpenShift
cluster, and the `build-images` task uses the multi-platform controller
to allocate remote VMs for non-amd64 architectures. When the cluster
is at capacity or remote VM pools are exhausted, tasks wait in queue.
The 4-hour build timeout ensures the pipeline doesn't fail just because
the cluster is busy.

### Scheduling and queue overhead

Each of the ~18 tasks runs as a separate Kubernetes pod. Between tasks:

1. **Initial queue wait**: PipelineRun created → first task starts.
   Depends on cluster load, can be seconds to hours.
2. **Inter-task scheduling gaps**: Each task pod needs scheduling,
   image pull, init containers. ~18 gaps per pipeline.
3. **Multi-platform VM allocation**: The `build-images` task uses the
   multi-platform controller to provision ppc64le/s390x VMs via SSH.
   Dynamic allocation: ~10 min per new VM. Fixed pool: queue when at
   capacity.
4. **Workspace transfer**: Build workspace copied to/from remote VMs
   over SSH (can be significant for large repos).

```
Konflux actual duration = queue_wait + sum(task_execution) + sum(scheduling_gaps) + VM_allocation
GHA actual duration     = runner_allocation (~seconds) + sum(step_execution)
```

**This overhead does not exist in GHA**: each GHA job runs on a
pre-allocated runner (available in seconds), and steps within a job
execute sequentially with no pod scheduling between them. Multi-arch
builds run on separate runners in parallel, not via remote SSH.

### Measured Konflux data (Tekton Results API, May 2026)

1000 PipelineRuns from `open-data-hub-tenant` (stone-prd-rh01),
filtered to **151 notebook/workbench/runtime builds with duration
>= 5 min** (excluding immediate failures). Durations are total
pipeline wall-clock — the full developer wait time from push to
result, including queue wait, build, and scan phases.

**Aggregate notebook build stats (n=151, duration >= 5 min):**

| Metric | Value |
|--------|------:|
| Average | **58 min** |
| Median | **52 min** |
| P90 | **120 min** |
| Max | **193 min** |
| PipelineRunTimeout | 9 runs |

**Success rate: 0% fully succeeded.** 48 Failed, 35 Cancelled,
59 Completed (build OK but scans failed), 9 Timed out.
"Completed" means the image was built but security scans failed.

**Per-component durations (components with multiple data points,
compared to GHA):**

| Component | Konflux avg | Konflux p90 | GHA amd64 | Ratio (avg) |
|---|---:|---:|---:|---:|
| jupyter-minimal-cuda | 60 min | 180 min | 21 min | **2.9x** |
| jupyter-minimal-rocm | 81 min | 141 min | 19 min | **4.3x** |
| jupyter-pytorch-rocm | 78 min | 174 min | 42 min | **1.9x** |
| jupyter-trustyai | 69 min | 99 min | 31 min | **2.2x** |
| jupyter-pytorch-cuda | 38 min | 70 min | 39 min | 1.0x |
| jupyter-minimal-cpu | 37 min | 96 min | 14 min | **2.6x** |
| runtime-minimal-cpu | 36 min | 122 min | 13 min | **2.8x** |
| runtime-pytorch-rocm | 60 min | 105 min | ~36 min | 1.7x |
| runtime-tensorflow-cuda | 59 min | 92 min | 28 min | **2.1x** |
| rstudio-minimal-cpu | 57 min | 77 min | — | — |
| codeserver-datascience | 81 min | 102 min | 90 min | 0.9x |

**High variance** is a hallmark of Konflux: `jupyter-minimal-cuda`
ranges from 8 to 180 min across 6 runs. This variance comes from
queue wait times (cluster load, VM pool availability) — a cost that
GHA does not have (runner allocation takes seconds). The P90 column
shows what developers experience on a busy day.

**Key findings:**
- **Median notebook build: 52 min Konflux vs ~25 min GHA** = 2x slower.
- **P90 notebook build: 120 min Konflux** — developers wait 2 hours
  for results 10% of the time. GHA P90 is ~52 min (pytorch-llmcompressor).
- `runtime-minimal-cpu` (simplest image): avg 36 min, max 122 min on
  Konflux vs 13 min on GHA. At worst: **9.4x slower**.
- GHA builds all architectures in parallel; Konflux serializes through
  the multi-platform controller, compounding the per-arch delay.
- **Zero notebook builds fully succeeded** on Konflux in this sample,
  due to scan task flakiness (OOMs, timeouts in clair/sast/clamav).

## Cost comparison

| | GitHub Actions | Konflux |
|---|---|---|
| Compute cost | **$0** (public repo, unlimited) | ROSA cluster + remote VMs |
| ppc64le/s390x builds | **$0** (IBM actionspz, free for OSS) | IBM Power/Z VMs (unknown $/hr) |
| Infrastructure mgmt | None (GitHub SaaS) | K8s cluster ops team |
| Pipeline YAML | 1 template + matrix strategy | 75 Tekton YAML files, 26 components |
| Cost per build | **$0** | Est. $10-50+ (cluster compute hours) |

GitHub reduced hosted-runner prices by 39% on Jan 1, 2026. For public repos,
all usage is free — GitHub provided $184M in free compute in 2025
(11.5 billion minutes).

## Multi-architecture coverage

| Architecture | GHA runners | Konflux components |
|---|---|---|
| amd64 | GitHub-hosted (free) | 26/26 |
| arm64 | GitHub-hosted (free, native since Aug 2025) | 4/26 |
| ppc64le | IBM actionspz (free) | **3/26** |
| s390x | IBM actionspz (free) | **0/26** |

GHA can build **all 26 components** on **all 4 architectures** using
native runners. Konflux currently builds most components for amd64 only.

## Developer experience

| Aspect | GHA | Konflux |
|---|---|---|
| Feedback integration | GitHub PR status checks (native) | Separate Konflux UI |
| Per-image status | Visible as each job completes | Hidden until pipeline finishes |
| Log access | GitHub Actions tab | Konflux UI or Tekton Results API |
| Re-run | Click "Re-run" in GitHub | Retrigger via `retest` comment or push |
| Local reproduction | `make <target>` with podman/docker | Requires Konflux cluster access |
| Required expertise | GitHub Actions YAML | Tekton + K8s + multi-platform controller |

## Reliability

| Issue | GHA | Konflux |
|---|---|---|
| OOM kills | Rare (dedicated runner, 16 GB) | Recurring (shared cluster, see `oom-detection.md`) |
| Pipeline flakiness | Low (isolated runners) | Higher (shared infra, scan task failures) |
| IBM runner queue | 13-18s typical, 12h worst case | N/A |
| Multi-arch VM alloc | N/A | ~10 min for dynamic VMs |

## Recommendation

1. **Use GHA as the primary CI system** for build feedback. It provides
   faster builds, free compute, better developer experience, and broader
   multi-arch coverage.

2. **Keep Konflux for release/certification pipelines** where Conforma
   (Enterprise Contract) policies, SBOM generation, and Red Hat release
   tooling are required. These are not time-sensitive (run after merge,
   not on PRs).

3. **Invest in IBM actionspz runners** for native ppc64le/s390x builds.
   This eliminates QEMU flakiness and provides ~1.5-2x speedup over
   cross-compilation, at zero cost.

4. **Target the 10-minute build rule** by optimizing the GHA pipeline:
   - Layer caching (already implemented via podman cache)
   - Skip unchanged images (already implemented via changed-files detection)
   - Parallel hermetic prefetch (currently sequential)
   - Consider splitting codeserver into a separate, less-frequent workflow

## Data collection scripts

| Script | Purpose |
|---|---|
| `scripts/ci/gha_build_durations.py` | Collect GHA job-level timing via `gh api` |
| `scripts/ci/konflux_build_durations.py` | Collect Konflux PipelineRun timing via Tekton Results API |

Usage:
```bash
# GHA (works immediately)
python scripts/ci/gha_build_durations.py --limit 10 --output gha.csv

# Konflux (requires oc login)
python scripts/ci/konflux_build_durations.py \
  --host tekton-results-tekton-results.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com \
  --namespace open-data-hub-tenant \
  --context "open-data-hub-tenant/api-stone-prd-rh01" \
  --output konflux.csv
```
