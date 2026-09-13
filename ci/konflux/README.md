# Per-architecture Konflux PipelineRuns (`ci/konflux/`)

Generates one Konflux **PipelineRun per (image, architecture)** so images and
architectures build in parallel — each run builds a single platform, then runs
the GHA test suite **in parallel** (one Tekton task/pod per test group),
instead of the serial single-job flow in
`.github/workflows/build-notebooks-TEMPLATE.yaml`.

The design (and the alternatives considered) is documented in the ADR under
`docs/architecture/decisions/` (search: "per-architecture").

## Why `.tekton/konflux/` and not `.konflux/`

Pipelines-as-Code only scans `.tekton/` — the directory name is a hardcoded
constant in the PaC source (`pkg/pipelineascode/pipelineascode.go: tektonDir = ".tekton"`),
with no configuration or symlink support. Files outside `.tekton/` are never
auto-triggered on PR events. The subdirectory `.tekton/konflux/` is supported
(PaC walks the tree recursively) and keeps these experimental files visually
separate from the other generated `.tekton/*` pipelines. This package keeps
the `konflux` name for the generator itself.

## Layout

| Path | What |
|------|------|
| `ci/konflux/generate_pipelineruns.py` | The generator (image inventory + pipeline templates + embedded unit tests) |
| `.tekton/konflux/<component>-<arch>-pull-request.yaml` | Generated PipelineRuns (do not edit by hand) |

Arch matrix per flavor (matches the existing Konflux multi-arch pipelines):

| Flavor | Architectures |
|--------|---------------|
| cpu | x86_64, arm64, ppc64le, s390x |
| cuda | x86_64, arm64 |
| rocm | x86_64 |

**Naming note:** K8s object names must be RFC 1123 (lowercase alphanumerics and
`-`), so the `x86_64` arch token is spelled `amd64` in the PipelineRun name and
filename (`...-amd64-pull-request.yaml`). `x86_64` remains in the Konflux
platform id (`linux/x86_64`), the image tag (`on-pr-<sha>-x86_64`), and the
on-comment trigger — those are plain string values, not K8s names.

**v1 scope:** `jupyter-minimal` (cpu) only, and tests only on `x86_64`.
Non-amd64 images would need qemu binfmt in the test pod (impractical for
ppc64le/s390x). Add images by extending the `IMAGES` list in the generator;
per-image test arches via the `test_arches` field.

## Regenerating

```bash
PYTHONPATH=. uv run ci/konflux/generate_pipelineruns.py
```

Bundle digests for the build-stage tasks are parsed from
`.tekton/multiarch-odh-main-combined-pipeline.yaml`, so keeping that file
updated keeps the generated pipelines in sync.

## Pipeline shape (per image x arch)

```text
init -> clone-repository -> prefetch-dependencies -> build-images -> build-image-index
                                          (all skipped when skip-build=true)

then, in parallel (two test legs, each its own pod, same sidecar design):
  test-testcontainers   pytest tests/containers (cpu markers)
  test-papermill        pytest tests/containers -m papermill — the GHA
                        papermill leg (make deploy/test) as a cluster-free
                        pytest port
```

Both test legs run the image under test as a Tekton **sidecar** of the test
pod and drive it through the sidecar exec agent (`tests/containers/
sidecar_agent.py`) over a localhost control plane — no container runtime in
the pod, no cluster. The GHA papermill test deploys the image to a kind
cluster and papermills `test_notebook.ipynb` in the notebook pod; the pytest
port (`tests/containers/workbenches/papermill_test.py`) runs the same
assertion against a plain container (the kind cluster never did anything the
container transport could), and the GHA `openshift`-marked pytest is
deferred to a real test cluster (EPHC/CSO — see the ADR).

Notes:

- **One build per run.** `build-platforms` is a single element; the
  `build-images` matrix degenerates to one TaskRun. Output tag is
  `on-pr-<sha>-<arch>` so per-arch runs never clobber the multi-arch
  `on-pr-<sha>` index the existing `.tekton/*` pipelines produce.
- **Image expiration: 5 days** (`image-expires-after: 5d`), same as the
  existing PR pipelines.
- **Sidecar test design (no in-pod runtime, no cluster).** In-pod container
  runtimes are impossible in this tenant: the SCCs reject `privileged: true`
  (verified live), rootless is voided by `NoNewPrivs: 1`, and the per-step
  `capabilities.add: [SYS_ADMIN]` probe was rejected at admission
  (`capability may not be added`). The test legs therefore run the image
  under test as a plain pod **sidecar** whose main process is the sidecar
  exec agent; the test step — the image under test itself, which ships
  git/curl/python3/uv (no dnf installs; runAsUser 0) — drives it over a
  localhost HTTP control plane. The k8s exec API was probed
  and rejected by RBAC (the pipeline SA cannot even `get pods`), so the agent
  is the only in-pod transport. Full evidence and the out-of-pod options map
  (mapt kind-on-AWS, EPHC/CSO `TestPlatformCluster` claims — the paths for
  the deferred `openshift`-marked tests) are in the ADR's Investigation
  section.
- **The papermill leg is cluster-free.** GHA's `make deploy9/test` deploys
  the image to a kind cluster only to host the image; the papermill
  execution itself (`test_notebook.ipynb` + `expected_versions.json` from the
  imagestream manifest) works identically against a plain container, so the
  pytest port runs it in the sidecar.
- **Scans are intentionally not in v1** (build + tests only, matching the
  GHA job which does trivy + FIPS, not the Konflux scan set). The existing
  multi-arch pipelines still cover scans; a generator flag can add them.

## Triggers

- **Auto (iteration mode):** every push to a PR targeting `main` triggers all
  four runs (no `pathChanged()` guard — deliberate, see the generator's
  `cel_expression()`). **Before this graduates, add a `pathChanged()` guard or
  switch to on-comment-only**, or every unrelated PR will burn four builds.
- **Manual:** per-arch PaC comment triggers, e.g.
  `/build-jupyter-minimal-cpu-x86_64` (CEL is bypassed for on-comment).
- `cancel-in-progress: true` — a new push cancels the in-flight runs.

## Fast iteration on the test stages

To iterate on the test tasks without rebuilding the image, override the
pipeline params (e.g. via the Konflux UI's "run pipeline" form or a temporary
param in the generated file):

```yaml
- name: skip-build
  value: "true"
- name: output-image
  value: quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:<any-existing-tag>
```

`skip-build=true` skips clone/prefetch/build (and the scans, when added);
`output-image` is the single source of truth for the image under test in
**both** modes — the built `on-pr-<sha>-<arch>` tag normally, or the existing
image to test here. The test sidecars pull it directly, so it must always be
a pullable reference.

## Observing runs

- The Konflux UI for the `open-data-hub-tenant` tenant, or the PR's
  GitHub checks.
- CLI: `oc get pipelinerun -n open-data-hub-tenant` (tenant users can list
  runs but not create them; triggering goes through PaC). Note the tenant
  GCs pod logs shortly after a failure, so for failed runs the KubeArchive
  export (used by the agent skills) is the durable log source.
- Failure triage: the `konflux-analyze` / `konflux-logs` agent skills.
