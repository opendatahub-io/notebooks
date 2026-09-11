# 18. Per-architecture Konflux PipelineRuns with parallel in-pod tests

Date: 2026-09-11

## Status

Proposed (draft [PR #4566](https://github.com/opendatahub-io/notebooks/pull/4566), iterating)

## Context

Notebook images are tested in two places that don't talk to each other:

- **Konflux** (`.tekton/*-pull-request.yaml`) builds every image for all
  supported architectures in one PipelineRun per image — build and scan only.
- **GitHub Actions**
  (`.github/workflows/build-notebooks-TEMPLATE.yaml`) re-builds the image
  and then runs the test suite **serially in a single job**:
  build → testcontainers pytest → `make deploy9/test/undeploy9`
  (papermill) → openshift pytest.

So each PR runs the build twice (GHA + Konflux), the test suite runs
serially, and the Konflux build is not gated on any test result.

The goal is to move the whole GHA job — build **and** tests — into Konflux,
with one PipelineRun per **(image, architecture)** pair so images and
architectures build in parallel, and with the test suite running **in
parallel**: each test group becomes its own Tekton task/pod.

### Design constraints that shaped the decision

Most of these were learned the hard way during the first live iterations of
PR #4566; they are recorded here so the pattern graduates without
re-discovering them.

1. **PaC only reads `.tekton/`.** The directory is a hardcoded constant in
   the Pipelines-as-Code source
   (`pkg/pipelineascode/pipelineascode.go`, `tektonDir = ".tekton"`); there
   is no configuration and no symlink support. The generated files therefore
   live in the `.tekton/konflux/` subdirectory (PaC walks the tree
   recursively), even though the generator package is named `ci/konflux/`.
2. **Inline `pipelineSpec`, not a Pipeline CR.** Tenant users cannot create
   or list Pipeline CRs (RBAC), so each PipelineRun embeds its full pipeline
   definition. The bundle pins for the build-stage tasks are parsed from
   `.tekton/multiarch-odh-main-combined-pipeline.yaml` at generation time,
   keeping a single source of truth for the digest pins.
3. **`taskRunSpecs` must only reference tasks that exist.** The test tasks
   are only present on test arches (v1: amd64); emitting a `taskRunSpecs`
   entry for a non-existent task fails the whole PipelineRun with
   `InvalidTaskRunSpecs`.
4. **`StepSpec.script` is a string.** Emitting the script as a YAML array
   fails Tekton validation ("cannot unmarshal array into … steps.script of
   type string"). PaC surfaces such schema errors as a PR comment from the
   `red-hat-konflux` bot and skips the file — the run never exists and no
   check run is created, which is easy to miss in a PR with many checks.
5. **K8s object names are RFC 1123.** The `x86_64` arch token contains an
   underscore, which the API server rejects for `metadata.name`
   (`generateName` too). The run name and filename use `amd64` (the K8s
   node-label spelling); `x86_64` stays where it is a plain string value
   (Konflux platform id `linux/x86_64`, image tag, on-comment trigger).
6. **`{{…}}` is PaC template syntax everywhere in the file.** Verified in
   the PaC source: templating is a regex replacement
   (`keys.ParamsRe = {{([^}]{2,})}}`); unknown keys are left as-is, so a
   stray `{{…}}` (e.g. a shell `--format '{{.Version}}'`) does not break the
   render — it just ends up as literal text in the PipelineRun. Avoid it
   anyway; the generator has a regression test for it.
7. **Iteration trigger has no `pathChanged()` guard.** The point of the
   experiment is to iterate by pushing to the PR branch, so the
   `on-cel-expression` fires on every PR push to `main`. **This must be
   changed (add `pathChanged()`, or go on-comment-only) before the pattern
   graduates**, or every unrelated PR triggers a full per-arch build fleet.

### Test-cluster choice: kind in a pod

GHA's "openshift" tests are a misnomer: the
`provision-k8s` action provisions a single-node **kubeadm** cluster — plain
k8s, not OpenShift (the workbench openshift-marked tests pass on plain k8s
via the `fake-scc` namespace-label trick). A single-node **kind** cluster in
a privileged Tekton pod is the faithful, near-free equivalent; GHA parity is
the bar for v1.

Real-OpenShift testing is the documented upgrade path: EPHC/CSO
(`TestPlatformCluster` claims, `provision-ephemeral-cluster` tasks from
`openshift/konflux-tasks`). The CRDs are verified present in the tenant
namespace, with a worked example in `opendatahub-io/odh-konflux-central`
(`integration-tests/olminstall/`), but the SA's RBAC for
`testplatformclusters` and the AWS cost per push (~10–20 min per cluster)
are not worked out yet. EAAS (what group-test uses today) remains the proven
fallback.

## Decision

Generate one Konflux **PipelineRun per (image, architecture)** from a Python
generator (`ci/konflux/generate_pipelineruns.py`), committing the output to
`.tekton/konflux/`. Each PipelineRun has an inline `pipelineSpec`:

```
init -> clone-repository -> prefetch-dependencies -> build-images (1 platform)
     -> build-image-index                    (all skipped when skip-build=true)

then, in parallel (one task/pod per test group):
  test-testcontainers                       podman (rootful) in a privileged pod
  provision-kind -> test-makefile-deploy    single-node kind cluster
                   -> test-openshift-pytest
```

- **v1 scope:** `jupyter-minimal` (cpu) only; tests only on amd64
  (non-amd64 test pods would need qemu binfmt, impractical for ppc64le/s390x).
  Arch matrix per flavor: cpu = amd64/arm64/ppc64le/s390x,
  cuda = amd64/arm64, rocm = amd64 (matching the existing multi-arch
  pipelines).
- **Build:** single-platform `build-images` (the matrix degenerates to one
  TaskRun); output tag `on-pr-<sha>-<arch>` so per-arch runs never clobber
  the multi-arch `on-pr-<sha>` index the existing `.tekton/*` pipelines
  produce. 5-day image expiration (`image-expires-after: 5d`), same as the
  existing PR pipelines.
- **Tests:** kind-in-pod for the makefile-deploy and openshift-pytest legs;
  podman-in-pod for testcontainers. `skip-build` + `image-under-test`
  params allow iterating on the test/provision stages without rebuilding.
- **Scans are out of scope for v1** (build + tests only); the existing
  multi-arch pipelines continue to cover them.

## Consequences

- **Parallel test pods per PR push.** One minimal-cpu PR push now triggers
  four builds plus (on amd64) four test pods, instead of one GHA job.
  Mitigations in place: v1 scope is a single image, `max-keep-runs: 3`,
  `cancel-in-progress: true`. Extending the `IMAGES` list is a one-liner but
  scales this linearly — re-evaluate before adding heavy images.
- **The tenant has a memory-request ResourceQuota (`konflux`, 1Ti).** Under
  fleet load the quota has been observed >99% used, and new 8Gi-request pods
  (prefetch/build) can fail with `ExceededResourceQuota`. This is transient
  and self-resolves as other pipelines finish — a re-trigger (or the next
  push) recovers it. The per-push 4x pipeline count raises the odds of
  hitting it; watch for this when triaging `prefetch-dependencies` failures.
- **Test pods need a privileged SCC.** kind + rootful podman require
  `securityContext.privileged: true` on the step. The per-component build
  SA's SCC was not directly verifiable (tenant RBAC hides serviceaccounts);
  if the test pods are rejected at admission, the fix is a dedicated SA with
  the `privileged` SCC or a rootless-podman variant of the test steps.
- **kind ≠ OpenShift.** Faithful to GHA, not an upgrade. EPHC is the
  documented upgrade path (see Context); it is deliberately not in v1.
- **The iteration trigger is not graduation-ready.** No `pathChanged()`
  guard (Constraint 7) — every PR push re-triggers the fleet. Graduation
  requires the guard or on-comment-only triggers.
- **Two PaC-visible artifacts per image now.** Until the GHA test job is
  retired, a PR builds the image in GHA *and* Konflux; the GHA job can then
  be deleted per-image as each image's Konflux runs prove out.
- **The generator is the source of truth.** Hand-editing
  `.tekton/konflux/*.yaml` is overwritten; the generator has embedded unit
  tests (including regression tests for Constraints 3–6) and is runnable
  with `PYTHONPATH=. uv run ci/konflux/generate_pipelineruns.py`.
  It is not yet wired into `ci/generate_code.sh` (that script doesn't cover
  any `.tekton/` generator today).

## References

- [PR #4566](https://github.com/opendatahub-io/notebooks/pull/4566) — the
  implementing PR (draft, iterating).
- [`ci/konflux/README.md`](../../../ci/konflux/README.md) — layout, triggers,
  iteration workflow, EPHC upgrade notes.
- `.github/workflows/build-notebooks-TEMPLATE.yaml` — the GHA job being
  duplicated (serial build+test reference).
- ADR [0016](0016-route-amd64-konflux-builds-to-in-cluster-x86-64.md) —
  amd64 in-cluster build routing and per-image resource sizing (the
  `taskRunSpecs` build sizing here follows its peak-aligned numbers).
- [`docs/konflux.md`](../../konflux.md) — operational Konflux reference.
- `openshift-pipelines/pipelines-as-code` source — `.tekton/` hardcoding
  (`pkg/pipelineascode/pipelineascode.go`) and template semantics
  (`pkg/templates/templating.go`, `pkg/apis/pipelinesascode/keys/keys.go`).
- `openshift/konflux-tasks` — `provision-ephemeral-cluster` /
  `deprovision-ephemeral-cluster` tasks (EPHC upgrade path).
