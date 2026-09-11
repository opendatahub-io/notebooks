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
a Tekton pod is the faithful, near-free equivalent; GHA parity is the bar
for v1.

The pod cannot be privileged: **the tenant's SCCs forbid it.** This was
verified live — the test pods failed at 0s with
`unable to validate against any security context constraint`, and every SCC
usable by the per-component build SA (`build-pipeline-<component>`) rejects
`.containers[0].privileged=true` (including the Konflux
`appstudio-pipelines-scc` and the cluster `privileged` SCC, which the SA
simply isn't bound to). The tenant RBAC does not let us read SAs/SCCs or
create bindings. The rootless path that followed was then proven
impossible in this tenant as well (`NoNewPrivs: 1` voids the setuid/filecap
prerequisite; no `CAP_SYS_ADMIN` for rootful) — see the
[Investigation](#investigation-in-pod-test-stages-in-this-tenant-2026-09-11)
section, including the open probe of whether the SCC allows a per-step
`capabilities.add: [SYS_ADMIN]`.

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

```text
init -> clone-repository -> prefetch-dependencies -> build-images (1 platform)
     -> build-image-index                    (all skipped when skip-build=true)

then, in parallel (two test legs, each its own rootless pod):
  test-testcontainers   rootless podman; testcontainers pytest
  test-k8s              rootless podman + kind, all in one step:
                        kind create -> make deploy/papermill -> openshift pytest
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
  podman-in-pod for testcontainers. Because privileged pods are forbidden,
  both legs run **rootless**: the step script creates a non-root user with a
  subuid range and re-execs its body as that user, then drives podman/kind
  rootless (`KIND_EXPERIMENTAL_PROVIDER=podman`). The kind cluster only lives
  inside its pod (and each Tekton step is its own container), so the whole
  k8s leg is a single step. `skip-build` + `image-under-test` params allow
  iterating on the test stages without rebuilding. (As of the
  [Investigation](#investigation-in-pod-test-stages-in-this-tenant-2026-09-11),
  the rootless form of this decision is infeasible in this tenant; the
  rootful form — step `capabilities.add: [SYS_ADMIN]` — is being probed.)
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
- **In-pod container runtimes are blocked in this tenant as configured —
  rootless and rootful alike.** The test pods were rejected at admission by
  every usable SCC with `privileged: true`, the rootless redesign was then
  proven impossible live (`NoNewPrivs: 1` makes setuid/filecaps on
  `newuidmap` void), and rootful podman/kind lacks `CAP_SYS_ADMIN`
  (`CapEff: 0x5fb`, the k8s default set). Full evidence and reproduction in
  the [Investigation](#investigation-in-pod-test-stages-in-this-tenant-2026-09-11)
  section; the open question it raises (whether the SCC permits a per-step
  `capabilities.add: [SYS_ADMIN]`, as the build task does for `SETFCAP`)
  decides between a rootful in-pod design and EPHC / a privileged SA.
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

## Investigation: in-pod test stages in this tenant (2026-09-11)

During live iteration of PR #4566, every in-pod container-runtime option was
tested against this tenant's pod security profile. **Result: no container
runtime (rootless or rootful) works in the test pods as configured.** The
build stage is unaffected — it works by a different mechanism (below).

### Finding chain (each step verified live)

1. **`privileged: true` — rejected at admission by every usable SCC.**
   `provider appstudio-pipelines-scc: .containers[0].privileged: Invalid
   value: true: Privileged containers are not allowed`; the cluster
   `privileged` SCC is `Forbidden: not usable by user or serviceaccount`.
   → rootless redesign (commit `b53516c62`).
2. **Rootless podman — `newuidmap` cannot write `uid_map`.**
   `newuidmap: write to uid_map failed: Operation not permitted ... should
   have setuid or have filecaps setuid`. The Fedora image ships
   `newuidmap`/`newgidmap` without setuid/filecaps.
3. **`setcap cap_setuid+ep` — EPERM.**
   `unable to set CAP_SETFCAP effective capability: Operation not
   permitted` — the test step lacks `CAP_SETFCAP`.
4. **Setuid bit — applied but void.** `ls -l` shows `-rwsr-xr-x` (the bit
   stuck), yet `write to uid_map failed` persists because the pod runs with
   **`NoNewPrivs: 1`** (pod spec: `allowPrivilegeEscalation: false`), which
   makes the kernel ignore setuid/filecaps on `execve`. **Rootless is
   categorically impossible in this tenant** — this is a tenant-wide
   property, not node-dependent.
5. **Rootful podman/kind — no `CAP_SYS_ADMIN`.** Step `CapEff` as root:
   `00000000000005fb` — the stock k8s default set (`chown, dac_override,
   fowner, fsetid, kill, setgid, setuid, setpcap, net_bind_service,
   net_admin, net_raw`), no `sys_admin`. Rootful podman/kind needs it for
   mount/network namespaces.
6. **testcontainers leg — no docker socket can exist.** pytest died with
   an `INTERNALERROR` connecting to the socket; consistent with 1–5.

### Why the build stage works under the same profile

The build task is `buildah-remote-oci-ta` (bundle
`quay.io/konflux-ci/tekton-catalog/task-buildah-remote-oci-ta:0.10.5`,
source `konflux-ci/build-definitions`). Two mechanisms keep it inside the
pod's capability budget:

- **The step requests capabilities explicitly**: its `securityContext` is
  `{"runAsUser": 0, "capabilities": {"add": ["SETFCAP"], "drop":
  ["MKNOD"]}, "allowPrivilegeEscalation": false}` — admission accepts the
  addition, i.e. **the SCC's `allowedCapabilities` list extends beyond the
  k8s defaults and per-step `capabilities.add` works in this tenant**.
- **buildah's chroot isolation creates no namespaces and does no mounts**:
  the in-cluster path (log line `Localhost detected; running build in
  cluster`) runs `konflux-build-cli image build` in-pod; RUN steps execute
  via `chroot(2)` into the on-disk rootfs (allowed for root on a
  root-owned directory without `CAP_SYS_CHROOT`) and inherit the pod's
  network namespace — so the whole build fits in the default cap set under
  `no_new_privs`. (Non-amd64 platforms instead rsync/ssh the build to a
  remote builder VM and only orchestrate in-pod.) podman/kind have no such
  mode: every container they create needs namespace + mount privileges.

### Open question: can the test step request `SYS_ADMIN`?

Finding 3+5 together imply a probe: the SCC allows per-step
`capabilities.add` (proven by the build step's `SETFCAP`). If
`sys_admin` is on that allow list, **rootful** podman/kind work in-pod
(`no_new_privs` is irrelevant — a process that already holds the caps can
`unshare`/`mount`; no setuid tricks involved), and the test design becomes:
step `securityContext: {runAsUser: 0, capabilities: {add: ["SYS_ADMIN"]}}`,
body runs as root, rootful podman socket. The probe is one push: admission
either rejects it at 0s (error names the SCC → in-pod is out, go EPHC /
privileged SA) or the rootful `podman info`/`kind create` proceeds.

### Reproduction

```bash
CTX='open-data-hub-tenant/api-stone-prd-rh01-pg1f-p1-openshiftapps-com:6443/jdanek'
KA_HOST="https://kubearchive-api-server-product-kubearchive.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com"
TOKEN=$(oc --context "$CTX" whoami -t)
NS=open-data-hub-tenant

# PLR -> TaskRuns
curl -s -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/$NS/pipelineruns/<plr>" |
  jq -r '.status.childReferences[] | "\(.pipelineTaskName)  \(.name)"'
# TaskRun -> pod
curl -s -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/apis/tekton.dev/v1/namespaces/$NS/taskruns/<tr>" | jq -r .status.podName
# step log (plain k8s pod-log API; NOT the tekton.dev logs path)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/api/v1/namespaces/$NS/pods/<pod>/log?container=step-test"
# pod security profile (securityContext per container)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$KA_HOST/api/v1/namespaces/$NS/pods/<pod>" |
  jq '.spec | {serviceAccountName, containers: [.containers[] | {name, securityContext}]}'
# decode the observed CapEff
capsh --decode=00000000000005fb
```

The generated test step also prints `CapEff`/`NoNewPrivs` (root phase, as
root) at the start of every run — the easiest live read.

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
