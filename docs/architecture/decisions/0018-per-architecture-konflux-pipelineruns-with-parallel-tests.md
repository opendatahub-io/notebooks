# 18. Per-architecture Konflux PipelineRuns with parallel sidecar tests

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
8. **The PR-comment report block is best-effort.** The tenant GCs pod logs
   within ~2 min of failure, so each test leg posts a pytest summary as a PR
   comment (via the PaC `git-auth` secret, key `git-provider-token`).
   Observed failure mode: the block wrote the report JSON with `printf` but
   never executed the generator script, so `curl --data-binary @/tmp/report.json`
   failed with `CURLE_READ_ERROR` (exit 26) and — under
   `set -Eeuxo pipefail` — killed the step, turning a green test run red.
   The generated block therefore runs the generator before the curl and
   makes the curl non-fatal (`|| true`): report delivery must never mask the
   test result.
9. **The sidecar image is a static param reference — it must resolve in
   every mode.** A container `image` field cannot do runtime fallback: when
   the sidecar was wired to a mode-only param (`image-under-test`, empty in
   build mode), Tekton failed pod creation with `missing field(s):
   sidecars.image` on both test tasks even though the build stage was green.
   Fix: one param is the single source of truth for the image under test in
   all modes — `output-image` (the built tag normally, the existing image
   when `skip-build=true`).

### Test-cluster choice: kind in a pod (superseded — see Decision)

GHA's "openshift" tests are a misnomer: the
`provision-k8s` action provisions a single-node **kubeadm** cluster — plain
k8s, not OpenShift (the workbench openshift-marked tests pass on plain k8s
via the `fake-scc` namespace-label trick). A single-node **kind** cluster in
a Tekton pod was the original faithful, near-free equivalent; GHA parity is
the bar for v1.

The pod cannot be privileged: **the tenant's SCCs forbid it.** This was
verified live — the test pods failed at 0s with
`unable to validate against any security context constraint`, and every SCC
usable by the per-component build SA (`build-pipeline-<component>`) rejects
`.containers[0].privileged=true` (including the Konflux
`appstudio-pipelines-scc` and the cluster `privileged` SCC, which the SA
simply isn't bound to). The tenant RBAC does not let us read SAs/SCCs or
create bindings. Every in-pod path was then proven impossible live: the
rootless path is voided by `NoNewPrivs: 1` (the setuid/filecap prerequisite
can't take effect), and a per-step `capabilities.add: [SYS_ADMIN]` probe was
rejected by the SCC (`capability may not be added`) — see the
[Investigation](#investigation-in-pod-test-stages-in-this-tenant-2026-09-11)
section for the full chain and reproduction.

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

then, in parallel (two test legs, each its own pod, same sidecar design):
  test-testcontainers   pytest tests/containers (cpu markers)
  test-papermill        pytest tests/containers -m papermill — the GHA
                        papermill leg (make deploy/test) as a cluster-free
                        pytest port
```

Both test legs run the image under test as a Tekton **sidecar** of the test
pod and drive it through the sidecar exec agent
(`tests/containers/sidecar_agent.py`) over a localhost HTTP control plane —
no container runtime in the pod, no cluster. The agent is embedded in the
generated task at generation time and handed to the sidecar over a shared
`emptyDir`; the sidecar's main process is the agent (which relaunches the
image's own entrypoint as a child on `/start`). The k8s exec API was probed
and rejected by RBAC (the pipeline SA cannot even `get pods`), so the agent
is the only in-pod transport.

The test **step** also runs in the image under test (`$(params.BUILT_IMAGE)`,
`runAsUser 0` — the workbench images' default user is 1001): these images
ship bash/git/curl/tar/python3/uv, so the step needs no package-manager
installs (no `dnf`), and the pod's image pull is shared with the sidecar.
The papermill leg runs pytest with `--capture=no` (it selects exactly one
test) so the papermill run output streams to the task log on success — GHA
parity; the test prints the output and the same text lands in the PR
comment's tail.

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
- **Tests:** both legs are sidecar-based (above) — no container runtime and
  no cluster in the test pod, so the tenant's pod-security constraints are
  irrelevant to the test stage. The GHA papermill leg
  (`make deploy9-<target>/test-<target>/undeploy9`) is ported to a cluster-free
  pytest test (`tests/containers/workbenches/papermill_test.py`, marker
  `papermill`): GHA's kind cluster only *hosts* the image — the papermill
  execution itself (`test_notebook.ipynb` + `expected_versions.json` from the
  imagestream manifest annotations) works identically against a plain
  container, which the sidecar transport provides. The GHA
  `openshift`-marked pytest is **not ported**: it needs a real cluster, so it
  is deferred to the out-of-pod options below (EPHC/mapt). The `skip-build`
  param allows iterating on the test stages without rebuilding; in that mode
  the caller overrides `output-image` (the single source of truth for the
  image under test in both modes — the test sidecars pull it directly, so an
  empty or stale reference fails pod admission).
- **Scans are out of scope for v1** (build + tests only); the existing
  multi-arch pipelines continue to cover them.

## Consequences

- **Parallel test pods per PR push.** One minimal-cpu PR push now triggers
  four builds plus (on amd64) two sidecar test pods, instead of one GHA job.
  Mitigations in place: v1 scope is a single image, `max-keep-runs: 3`,
  `cancel-in-progress: true`. Extending the `IMAGES` list is a one-liner but
  scales this linearly — re-evaluate before adding heavy images.
- **The tenant has a memory-request ResourceQuota (`konflux`, 1Ti).** Under
  fleet load the quota has been observed >99% used, and new 8Gi-request pods
  (prefetch/build) can fail with `ExceededResourceQuota`. This is transient
  and self-resolves as other pipelines finish — a re-trigger (or the next
  push) recovers it. The per-push 4x pipeline count raises the odds of
  hitting it; watch for this when triaging `prefetch-dependencies` failures.
- **In-pod container runtimes are impossible in this tenant — all four
  combinations exhausted.** `privileged: true` is rejected by every usable
  SCC; rootless is voided by `NoNewPrivs: 1` (setuid/filecaps on
  `newuidmap` can't take effect); rootful + per-step
  `capabilities.add: [SYS_ADMIN]` is rejected by the SCC
  (`capability may not be added`); rootful with the default caps
  (`CapEff: 0x5fb`) lacks `CAP_SYS_ADMIN`. Full evidence and reproduction in
  the [Investigation](#investigation-in-pod-test-stages-in-this-tenant-2026-09-11)
  section. **This is what shaped the sidecar design**: a sidecar container
  needs no runtime, no capabilities, no cluster, and the pytest suite was
  already transport-agnostic (the same tests run against podman/docker, the
  sidecar agent, or a kind-deployed workload).
- **The `openshift`-marked tests are deliberately not in v1.** They need a
  real cluster (the sidecar transport covers "the image as a workload", not
  "a cluster to deploy into"). The out-of-pod options map (mapt kind-on-AWS,
  mapt Fedora VM, EPHC, privileged SA, EAAS, build-only) in
  [Options for the test stage](#options-for-the-test-stage-out-of-pod) is
  the upgrade path — decision pending.
- **The papermill leg needs no cluster at all.** GHA's
  `make deploy9/test/undeploy9` exists only to host the image; the pytest
  port (`-m papermill`) runs the same notebook against the sidecar, so that
  GHA leg graduates on day one. Verified live: the ported test passes in a
  real Konflux-sidecar-shaped pod against the built image.
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
runtime works in the test pods — `privileged` (rejected), rootless
(`NoNewPrivs`), rootful + `CAP_SYS_ADMIN` (rejected), rootful with default
caps (insufficient).** The build stage is unaffected — it works by a
different mechanism (below).

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
7. **Per-step `capabilities.add: [SYS_ADMIN]` — rejected at admission.**
   The probe run (commit `ab9b7ffd8`) was rejected by the SCC with:
   `provider appstudio-pipelines-scc: .containers[0].capabilities.add:
   Invalid value: "SYS_ADMIN": capability may not be added`. The SCC's
   `allowedCapabilities` includes `SETFCAP` (the build task proves it) but
   not `sys_admin`.

**In-pod container runtimes are therefore impossible in this tenant, end of
story** — all four combinations are exhausted: `privileged: true` (1),
rootless user namespaces (2–4), rootful + `CAP_SYS_ADMIN` (5, 7), rootful
with the default caps (5).

**Resolution (added 2026-09-12):** rather than moving the test stage
out-of-pod, the design was inverted — the image under test runs as a Tekton
**sidecar** of the test pod (a plain container: no runtime to install, no
capabilities to request), and the pytest suite drives it through a small
sidecar exec agent over a localhost control plane. This closes findings 1–7
for both in-scope test legs: a sidecar needs none of the resources that
failed. (A k8s-exec-API transport was probed in parallel and rejected by
RBAC — the pipeline SA cannot even `get pods` — leaving the agent as the
only in-pod transport.) What remains out-of-pod is only the deferred
`openshift`-marked leg, for which the options below (dedicated privileged
SA, EPHC, EAAS) still apply.

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

### Probed: the test step cannot request `SYS_ADMIN` (resolved)

Findings 3+5 implied a probe: the SCC allows per-step
`capabilities.add` (proven by the build step's `SETFCAP`). If
`sys_admin` were on that allow list, **rootful** podman/kind would work
in-pod (`no_new_privs` is irrelevant — a process that already holds the
caps can `unshare`/`mount`; no setuid tricks involved). The probe
(commit `ab9b7ffd8`, run `...-amd64-on-pulldn7bk`) was rejected:
`capability may not be added` (finding 7). The in-pod option is closed.

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

### Options for the test stage (out-of-pod)

With in-pod closed (findings 1–7), the runtime/cluster has to come from
outside the tenant pods. Full breadth of options, mapped from the tenant's
own Slack (`#forum-konflux-devprod`, `#forum-ocp-testplatform`,
`#forum-ansible-product-delivery-engineering`) and Jira:

| # | Option | What runs where | Human ask | Provisioning | Tenant status |
|---|--------|----------------|-----------|--------------|---------------|
| A | **mapt kind-on-AWS** — `kind-aws-spot` task, `konflux-ci/tekton-integration-catalog` | kind cluster (plain k8s, v1.32 default) on an AWS spot EC2 (default 16 vCPU / 64 GiB, `x86_64`/`arm64`); pipeline steps use the generated kubeconfig | AWS-creds secret in the tenant ns + secret RBAC for the pipeline SA | minutes (mapt/Pulumi) | not used here yet; task needs no privileged pod |
| B | **mapt Fedora VM** — `fedora-virtual-machine` task | bare Fedora VM on AWS; whatever is installed runs there (podman, kind, both) | same as A | minutes | not used here yet |
| C | **EPHC / TestPlatformCluster** | full OpenShift cluster via a claim; steps use the connection secret | RBAC for `testplatformclusters` (unverified here); provider already installed in-tenant | 1h11m–1h42m observed (vanguard thread); tests themselves ~14m | proven in a sibling Konflux tenant, but the platform is deprecating it for PR-level tests (KONFLUX-7296) |
| D | **Dedicated privileged SA** | the current rootful in-pod code, nearly as-is (`capabilities.add` → `privileged: true` + per-task SA) | SCC binding grant — no evidence of a standard offering | n/a (in-pod) | unavailable; tenant-admin action |
| E | **EAAS** | the proven group-test fallback (see `docs/konflux.md`) | EAAS access for the repo | minutes | proven for a different test suite |
| F | **Build-only v1, tests stay on GHA** | — | none | — | status quo |

**A is the platform-endorsed path.** KONFLUX-7296 ("Refactor the
provisioning architecture used in Konflux CI pipelines", closed, FinOps)
directs Konflux components to **deprecate OpenShift ephemeral clusters for
PR-level e2e in favor of lightweight k8s (kind on AWS)**, reserving full
OpenShift for nightly. KFLUXDP-277 (the mapt kind tasks in the
integration catalog), KFLUXDP-245 (investigation) and KFLUXDP-271
(release-service integration) are all closed/done. The tasks are in live
production in sibling tenants — `konflux-vanguard-tenant`
(konflux-operator-e2e), `rhtap-release-2-tenant`, `ansible-ci-tenant`
(aap-ui-e2e, jewel-atf-tests), `nexus-tenant` — and every failure mode
seen in Slack is AWS-side, not SCC-side: shared-account
`VpcLimitExceeded`, spot capacity (g5.2xlarge), rotated IAM keys
(`InvalidAccessKeyId`), the `g4ad.4xlarge` instance-type bug (mapt#902,
fixed in 0.3), S3 `GetBucketLocation`.

Task specifics (from the catalog, verified against the live
`konflux-ci/release-service` `integration-tests/pipelines/konflux-e2e-tests-pipeline.yaml`):

- **Wiring**: `taskRef` via the **git resolver** (
  `url: tekton-integration-catalog.git`, `revision: main`,
  `pathInRepo: tasks/mapt-oci/kind-aws-spot/provision/0.2/kind-aws-provision.yaml`)
  — no bundle pinning needed.
- **Provision params**: `secret-aws-credentials` (secret with
  `access-key`/`secret-key`/`region`/`bucket`), `id` (pipelineRun name),
  `cluster-access-secret-name: kfg-$(context.pipelineRun.name)`,
  `ownerKind/ownerName/ownerUid` = the PipelineRun (secrets are
  owner-referenced → GC'd with the run), `oci-ref`/`oci-credentials`
  (task-log storage), `spot-increase-rate: 80` (capacity workaround),
  optional `arch`/`cpus`/`memory`/`compute-sizes`, `version` (k8s,
  default v1.32 — matches GHA), `nested-virt`, `timeout` (auto-destroy),
  `extra-port-mappings` (expose NodePorts from the VM),
  `ssh-credentials-secret-name` (VM access: `host`/`username`/`id_rsa`).
- **Consumption**: the test task receives `cluster-access-secret` and the
  README's recommended pattern is a `stepTemplate` mounting that secret
  with `KUBECONFIG` set — `kubectl`/pytest run from the Tekton pod against
  the remote cluster.
- **Deprovision**: `kind-aws-deprovision` (0.1) with the same
  `secret-aws-credentials`/`id`, deleting VM + secrets.

Fit for the remaining (deferred) test leg:

- **`openshift`-marked pytest: near-exact GHA parity.** Remote kind (plain
  k8s, v1.32) — the openshift markers pass on plain k8s via the `fake-scc`
  namespace-label trick, exactly as in GHA — with the pytest run from the
  Tekton pod via the mounted kubeconfig; no in-pod runtime at all.
  (The sidecar legs need none of this: they run in-pod with no cluster.)

So the human ask for A/B is one item: an AWS-credentials secret in
`open-data-hub-tenant` (onboarding team; standard for tenants using the
catalog — vanguard's secret is `konflux-mapt-us-east-1`, the 0.3 readme
shows `konflux-test-infra`, release-service uses `mapt-kind-secret`)
plus secret RBAC for the pipeline SA. Open risk to probe: the git
resolver inside a **PaC** pipeline in this tenant (release-service uses
it in an application-driven pipeline); the fallback is a bundle
reference to the same catalog.

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
- `konflux-ci/tekton-integration-catalog` — `tasks/mapt-oci/kind-aws-spot`
  (provision 0.1–0.3 / deprovision 0.1–0.2) and
  `tasks/mapt-oci/fedora-virtual-machine` (0.1); live wiring example in
  `konflux-ci/release-service`
  `integration-tests/pipelines/konflux-e2e-tests-pipeline.yaml`.
- [KFLUXDP-277](https://redhat.atlassian.net/browse/KFLUXDP-277) (mapt
  kind epic, closed), [KONFLUX-7296](https://redhat.atlassian.net/browse/KONFLUX-7296)
  (deprecate EPHC for PR-level e2e, closed), KFLUXDP-245, KFLUXDP-271.
