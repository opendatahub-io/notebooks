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

```
init -> clone-repository -> prefetch-dependencies -> build-images -> build-image-index
                                          (all skipped when skip-build=true)

then, in parallel:
  test-testcontainers                      podman (rootful) in a privileged pod;
                                           pytest tests/containers (cpu markers)
  provision-kind -> test-makefile-deploy   single-node kind cluster in a privileged
  |                  (make deploy9/test/undeploy9 via ci/cached-builds/make_test.py)
  -> test-openshift-pytest                 pytest tests/containers (openshift markers)
```

Notes:

- **One build per run.** `build-platforms` is a single element; the
  `build-images` matrix degenerates to one TaskRun. Output tag is
  `on-pr-<sha>-<arch>` so per-arch runs never clobber the multi-arch
  `on-pr-<sha>` index the existing `.tekton/*` pipelines produce.
- **Image expiration: 5 days** (`image-expires-after: 5d`), same as the
  existing PR pipelines.
- **Test cluster = kind in a privileged pod.** GHA's "openshift" tests
  actually run on a single-node *kubeadm* cluster (plain k8s, not OpenShift)
  via `.github/actions/provision-k8s` — kind is the faithful equivalent and
  costs nothing per push. Real-OpenShift testing is the documented upgrade
  path via **EPHC/CSO** (`TestPlatformCluster` claims,
  `provision-ephemeral-cluster` tasks from `openshift/konflux-tasks`; verified
  installed in `open-data-hub-tenant`, with a worked example in
  `opendatahub-io/odh-konflux-central:integration-tests/olminstall/`).
- **Test pods need a privileged SCC.** `kind`/rootful-podman require
  `securityContext.privileged: true`. If the per-component build SA
  (`build-pipeline-<component>`) lacks a privileged-capable SCC, the test
  pods will be rejected at admission — the fix is a dedicated SA with the
  `privileged` SCC (Konflux onboarding team) or a rootless-podman variant of
  the test steps.
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

## Fast iteration on the test/provision stages

To iterate on the test tasks without rebuilding the image, override the
pipeline params (e.g. via the Konflux UI's "run pipeline" form or a temporary
param in the generated file):

```yaml
- name: skip-build
  value: "true"
- name: image-under-test
  value: quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:<any-existing-tag>
```

`skip-build=true` skips clone/prefetch/build (and the scans, when added);
the test stages resolve the image under test from `image-under-test`.

## Observing runs

- Konflux UI: https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com
  (tenant `open-data-hub-tenant`), or the PR's GitHub checks.
- CLI: `oc get pipelinerun -n open-data-hub-tenant` (tenant users can list
  runs but not create them; triggering goes through PaC).
- Failure triage: the `konflux-analyze` / `konflux-logs` agent skills.
