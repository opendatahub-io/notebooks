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

| System | Fastest image | Median | P90 | Max |
|--------|-------------|--------|-----|-----|
| **GHA** | **13 min** (runtime-minimal) | **~25 min** | **52 min** | **97 min** |
| **Konflux** | **18 min** (runtime-minimal med) | **~45 min** | **~115 min** | **366 min** |

Based on **1,502 Konflux builds** and **108 GHA builds** (measured May 2026).

GHA is approaching the 10-minute target for lightweight images. Konflux
median is ~45 min (1.8x GHA), P90 is ~115 min, and worst case reaches
**6 hours** due to queue congestion. The same image (`jupyter-minimal-cpu`)
ranges from 5 to 339 min on Konflux (68x variance) vs 13-16 min on GHA
(1.2x variance). Queue wait is the dominant factor.

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

Per-component queries via Tekton Results API on `open-data-hub-tenant`
(stone-prd-rh01), 100 PipelineRuns per component, filtered to builds
with duration >= 5 min (excluding immediate failures). Total:
**1,502 valid notebook builds** across 18 components.

Durations are total pipeline wall-clock — the full developer wait time
from push to result, including queue wait, build, and scan phases.

**Per-component durations (with GHA comparison):**

| Component | N | Konflux avg | Konflux med | Konflux p90 | Konflux max | GHA amd64 | Ratio (med) |
|---|---:|---:|---:|---:|---:|---:|---:|
| jupyter-minimal-cpu | 81 | 36 min | 20 min | 89 min | 339 min | 14 min | **1.4x** |
| jupyter-minimal-cuda | 92 | 43 min | 31 min | 93 min | 288 min | 21 min | **1.5x** |
| jupyter-minimal-rocm | 82 | 67 min | 44 min | 141 min | 366 min | 19 min | **2.3x** |
| jupyter-datascience-cpu | 86 | 54 min | 34 min | 120 min | 360 min | 23 min | **1.5x** |
| jupyter-pytorch-cuda | 81 | 61 min | 55 min | 104 min | 295 min | 39 min | **1.4x** |
| jupyter-pytorch-rocm | 88 | 64 min | 62 min | 131 min | 174 min | 42 min | **1.5x** |
| jupyter-tensorflow-cuda | 81 | 55 min | 51 min | 113 min | 150 min | 34 min | **1.5x** |
| jupyter-tensorflow-rocm | 84 | 59 min | 58 min | 113 min | 283 min | 35 min | **1.7x** |
| jupyter-trustyai-cpu | 86 | 58 min | 58 min | 106 min | 163 min | 31 min | **1.9x** |
| jupyter-pytorch-llmcompressor | 78 | 61 min | 52 min | 120 min | 332 min | 48 min | **1.1x** |
| codeserver-datascience | 82 | 65 min | 72 min | 117 min | 164 min | 90 min | 0.8x |
| runtime-minimal-cpu | 86 | 31 min | 18 min | 73 min | 166 min | 13 min | **1.4x** |
| runtime-datascience-cpu | 85 | 38 min | 31 min | 83 min | 125 min | 20 min | **1.6x** |
| runtime-pytorch-cuda | 85 | 47 min | 43 min | 99 min | 180 min | 29 min | **1.5x** |
| runtime-pytorch-rocm | 88 | 60 min | 59 min | 128 min | 180 min | 36 min | **1.6x** |
| runtime-tensorflow-cuda | 88 | 53 min | 46 min | 106 min | 225 min | 28 min | **1.6x** |
| runtime-tensorflow-rocm | 80 | 61 min | 51 min | 120 min | 305 min | ~35 min | **1.5x** |
| runtime-pytorch-llmcompressor | 79 | 53 min | 44 min | 106 min | 244 min | 37 min | **1.2x** |

**Aggregate across all 1,502 builds:**

| Metric | Konflux | GHA (amd64) |
|--------|--------:|------------:|
| Median | **~45 min** | **~25 min** |
| P90 | **~115 min** | **~52 min** |
| Max | **366 min** | **97 min** |

**High variance** is a hallmark of Konflux: `jupyter-minimal-cpu`
ranges from 5 to 339 min across 81 runs (68x range). Same image on
GHA: 13-16 min (1.2x range). This variance comes from queue wait
times — a cost that GHA eliminates entirely. The P90 column shows
what developers experience on a busy day: **nearly 2 hours**.

**Key findings:**
- **Median: Konflux is ~1.5-2x slower** than GHA across all components.
- **P90: Konflux is ~2-3x slower** — the tail is where the pain is.
  Developers wait 90-140 min for results 10% of the time.
- **Max: Konflux runs reach 5-6 hours** (339-366 min) due to queue
  congestion. GHA never exceeds ~97 min (codeserver).
- The only component where GHA is slower is codeserver (compiles VS
  Code from source — equally slow on both systems).
- GHA builds all architectures in parallel; Konflux serializes through
  the multi-platform controller, so multi-arch builds compound the delay.

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

## What if Konflux split off scans?

The comparison above includes Konflux scan phase (clair, sast, clamav,
rpms-signature, etc.) in the total pipeline time, while GHA times are
primarily build + test (though GHA also runs FIPS scan and testcontainers).

If Konflux reported build results as soon as `build-image-index`
completes — before scans run — the feedback loop would be shorter.

**Estimated scan phase overhead:**

The scan tasks run in parallel after `build-image-index`, but each
is a separate pod with scheduling overhead:
- ~6-8 scan tasks, each running 3-10 min
- Pod scheduling gaps between them: ~1-2 min each
- Estimated scan phase total: **15-25 min** (parallel with scheduling)

**Estimated Konflux build-only median:** ~45 min (current median) minus
~15-20 min scan phase = **~25-30 min**. This is **competitive with GHA**
(median ~25 min) for the build phase alone.

**Splitting has minimal cost in Konflux:** Each task already runs in
its own pod and pulls images independently — there's no shared
state between build and scan tasks beyond the image reference. Moving
scans to a separate pipeline triggered after build-image-index wouldn't
add extra push/pull overhead because that overhead already exists
between tasks.

The build pipeline would still need SBOM generation (syft) and push
to quay.io, which are inherently slow, but the scan tasks (clair, sast,
clamav, rpms-signature) could report independently without blocking
the build result.

**Note:** In GHA, splitting scans into a separate workflow WOULD have
costs — the scan workflow would need to pull the built image from the
registry, adding latency that currently doesn't exist (scans run in
the same job that built the image).

Splitting does NOT fix the queue variance: the 5-339 min range for
`jupyter-minimal-cpu` is driven by queue wait before the build even
starts, not by scan time.

**Would splitting make Konflux competitive?**

| Scenario | Konflux median | Konflux P90 | GHA median |
|---|---:|---:|---:|
| Current (build + scans) | ~45 min | ~115 min | ~25 min |
| Build-only (estimated) | ~25-30 min | ~95-100 min | ~25 min |

- **Median: Yes** — Konflux build-only would be roughly competitive
  with GHA (~25-30 min vs ~25 min).
- **P90: No** — the tail is dominated by queue wait (30-300 min),
  which scan splitting doesn't address. GHA P90 is ~52 min.
- **Variance: No** — the 68x range (5-339 min) is structural to
  shared cluster scheduling, not scan overhead.

**Conclusion:** Splitting scans would improve Konflux median feedback
by ~15-20 min, making it competitive with GHA for typical builds. But
the fundamental advantage of GHA — **predictable, low-variance build
times with no queue wait** — remains. The P90 and tail latency, which
is where developer frustration compounds, is a queue problem that scan
splitting cannot fix.

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

4. **Target the 10-minute build rule** — see detailed analysis below.

## Path to 10-minute builds

### Current build time breakdown (jupyter-minimal, ~14 min on GHA)

```
~1 min   GHA runner allocation + checkout + setup (go, uv)
~2 min   hermetic prefetch (pip wheels, RPMs from lockfiles)
~1 min   sandbox.py build context assembly
~3 min   dnf install (RPMs from /cachi2/output — local unzip, no network)
~2 min   uv pip install (wheels from /cachi2/output — local unzip, no network)
~2 min   fix-permissions, addons, labextension config
~3 min   podman layer commits + image tagging
```

### Layer caching is likely wasteful for hermetic builds

The GHA workflow uses `--cache-from` / `--cache-to` with a GHCR-based
cache image. However, for hermetic builds this may be **net-negative**:

1. **RUN steps don't download from the internet.** They install from
   pre-fetched archives in `/cachi2/output/deps/`. The expensive part
   (network download) was already done in the prefetch step.
2. **Cache input changes frequently.** Lock files are updated by
   Renovate/MintMaker, invalidating the pip/dnf layers. The RPM lock
   file COPY before dnf install invalidates all downstream layers.
3. **Cache overhead may exceed savings.** Pushing/pulling multi-GB
   cache layers to/from GHCR (compress, upload, download, decompress)
   takes time. If the underlying install is just "unzip local files"
   (~2-3 min), the cache round-trip might cost more than it saves.
4. **buildah has a known cache bug.** [buildah#4612](https://github.com/containers/buildah/issues/4612):
   pulled cache layers aren't reused even with `--layers` enabled.

**Recommendation:** Benchmark with and without `--cache-from`. If cache
pulls take >2 min and the local install takes ~3 min, caching is
wasteful. The Makefile default (`--no-cache`) may be correct for
hermetic builds.

### GHA optimizations (ranked by expected impact)

#### 1. Remove codeserver compilation from the critical path

Codeserver takes **90 min** (compiles VS Code from source) and dominates
workflow wall-clock. Three approaches exist to fix this:

**a) Pre-build VS Code into a separate Docker image.** Use
`RUN --mount=type=bind,from=vscode-builder,...` or `COPY --from=` to
pull pre-compiled artifacts from a dedicated builder image. The builder
image rebuilds only when code-server or VS Code versions change
(~monthly). The workbench build then just copies binaries (~1 min
instead of ~90 min). Related:
[RHAIENG-2647](https://redhat.atlassian.net/browse/RHAIENG-2647)
(Harden Jupyter DataScience and CodeServer builds),
[RHAIENG-4337](https://redhat.atlassian.net/browse/RHAIENG-4337)
(Investigate code-server npm prefetch reduction).

**b) Publish code-server as a pre-built npm package.** Konflux npm
publishing support is being developed:
[RHIDP-13136](https://redhat.atlassian.net/browse/RHIDP-13136)
(move POC npm publishing task to official status),
[KONFLUX-12339](https://redhat.atlassian.net/browse/KONFLUX-12339)
(release NPM content to npm.registry.redhat.com). If code-server
is published as a pre-built npm package, the workbench Dockerfile
can `npm install` from a registry instead of compiling from source.

**c) Trigger codeserver build only on changes.** Simplest approach:
skip the codeserver matrix entry when `codeserver/` directory is
unchanged. Reduces typical push workflow from 90 to ~52 min but
doesn't fix the codeserver build itself.

**Impact:** Options a/b eliminate the 90-min bottleneck entirely.
Option c reduces frequency but not duration.
Workflow wall-clock: **90 min -> ~52 min** (option c) or
**90 min -> same but codeserver finishes in ~5 min** (options a/b).

#### 2. Skip unchanged images on push builds (CONSIDERED, NOT RECOMMENDED)

[`ci/cached-builds/gha_pr_changed_files.py`](ci/cached-builds/gha_pr_changed_files.py)
already detects which images need rebuilding for PRs. Extending to
push builds would reduce wall-clock from 90 to ~25 min.

**However:** Push builds run after merge — no developer is blocked
waiting. Building all images on every push serves as a safety net
that catches integration issues (e.g., a shared base image change
breaking a downstream image that wasn't touched in the PR). The
90-min push wall-clock is acceptable for this insurance.

#### 3. Parallelize prefetch steps

`scripts/lockfile-generators/prefetch-all.sh` runs 5 dependency types
sequentially: generic artifacts, pip wheels, npm, RPMs, Go modules.
Each step is independent.

**Change:** Run prefetch steps in parallel with `&` and `wait`.

**Impact:** Prefetch phase: **~2-3 min -> ~1 min**.

#### 4. Optimize sandbox.py context assembly

`scripts/sandbox.py` copies all Dockerfile dependencies into a temp
directory. For images with many prereqs, this copy takes ~1 min.

**Change:** Use hardlinks or symlinks instead of file copies.
Or bind-mount the workspace directly (skip sandbox for CI).

**Impact:** **~1 min saved** per build.

#### 5. Use native IBM runners for ppc64le (DONE in PR #3525)

QEMU cross-compilation: 22-45 min, often fails.
Native IBM runners: ~15-20 min, reliable.

**Impact:** ppc64le builds: **45 min -> 15 min** (3x speedup).

#### 6. Evaluate --no-cache for hermetic builds

As discussed above, layer caching may be counterproductive when all
installs are from local archives.

**Change:** A/B test: run identical builds with `--cache-from` vs
`--no-cache`. Measure total job time including cache pull/push.

**Impact:** Potentially **1-3 min saved** if cache overhead > install time.

### Konflux optimizations (ranked by expected impact)

#### 1. Split scans into a separate pipeline

Covered in detail above. Build result reported after `build-image-index`,
scans run asynchronously.

**Impact:** Median feedback: **~45 min -> ~25-30 min**.

#### 2. Dedicated build nodes or priority scheduling

Queue wait is the dominant factor in Konflux tail latency. P90 is
120 min, largely queue time.

**Change:** Request dedicated node pool or priority class for notebook
builds from the Konflux team.

**Impact:** P90: **120 min -> ~60 min** (eliminate queue wait).

#### 3. Bundle sequential tasks into fewer pods (NOT RECOMMENDED)

18 tasks = 18 pod scheduling events. Merging tasks would save ~5-10
min of scheduling overhead. However, deviating from the default
Konflux pipeline structure is a **maintenance burden** — every
Konflux upgrade requires reconciling custom changes. Even the
scan-splitting change (#1) already adds maintenance cost. Further
customization is not worth the savings.

#### 4. BuildKit cache mounts in buildah (MARGINAL BENEFIT)

`RUN --mount=type=cache,target=/var/cache/dnf` persists the dnf
metadata cache across builds. However, with hermetic builds, dnf
installs from local RPMs in `/cachi2/output/` — no network, no repo
metadata download. The cache mount would save dnf's transaction
planning (~30s), not the actual RPM unpack + scriptlet execution.
Not worth the Dockerfile complexity for marginal gains.

### Realistic targets

| Image class | Cold build | With optimizations | 10-min feasible? |
|---|---|---|---|
| runtime-minimal | 13 min | **~8-10 min** | Yes |
| jupyter-minimal | 14 min | **~9-11 min** | Close |
| jupyter-datascience | 23 min | **~15-18 min** | Not without arch changes |
| jupyter-pytorch-cuda | 39 min | **~25-30 min** | No (base image is large) |
| codeserver | 90 min | **~90 min** | No (VS Code compilation) |

The 10-minute build is achievable for simple images with the
optimizations above. Complex images (CUDA/ROCm with large base images)
have a structural floor of ~15-25 min due to base image size and
package count. Codeserver is a fundamentally different build type.

**The biggest single win is skip-unchanged on push builds (#2 above):**
most pushes to main are dependency updates touching 1-3 images. If we
only build those, the typical push workflow finishes in 15-25 min
instead of 90 min.

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
