# Quay.io image repositories

Notebook, runtime, and base images for this project are spread across several
[quay.io](https://quay.io) organizations. This page is the map for new contributors:
which organization holds what, which repositories are still in use, and how they
relate to each other.

The authoritative sources are the files in this repository. If this page disagrees
with them, the files win:

| Question | Source of truth |
|----------|-----------------|
| Where does an ODH build push? | `output-image` in [`.tekton/*-push.yaml`](../.tekton/) |
| Which base image does a build start from? | `BASE_IMAGE` in `<image-dir>/build-args/*.conf` |
| Which images does the ODH operator deploy? | [`manifests/odh/base/params*.env`](../manifests/odh/base/) |
| Which images does the RHOAI operator deploy? | [`manifests/rhoai/base/params.env`](../manifests/rhoai/base/) |

## Summary

| Repository | Contents | Built from | Status |
|------------|----------|------------|--------|
| `quay.io/opendatahub/odh-workbench-*`, `quay.io/opendatahub/odh-pipeline-runtime-*` | ODH workbench and Elyra runtime images, one repository per image | This repo, Konflux (`.tekton/`) | **Active** |
| `quay.io/opendatahub/odh-base-image-*-py312-c9s` | ODH CentOS Stream 9 base images (CPU, CUDA, ROCm) | This repo, [`base-images/`](../base-images/) | **Active** |
| `quay.io/opendatahub/odh-midstream-*` | Midstream Python/CUDA/ROCm base images | [opendatahub-io/base-containers](https://github.com/opendatahub-io/base-containers) | **Active** (input to ODH base images) |
| `quay.io/rhoai/odh-workbench-*-rhel9`, `quay.io/rhoai/odh-pipeline-runtime-*-rhel9` | RHOAI workbench and runtime images (dev, nightly, release candidates) | [red-hat-data-services/notebooks](https://github.com/red-hat-data-services/notebooks), Konflux | **Active** |
| `quay.io/aipcc/base-images/*` | RHOAI RHEL 9 base images (CPU, CUDA, ROCm) | AIPCC | **Active** (input to RHOAI builds) |
| `quay.io/modh/*` (e.g. `quay.io/modh/runtime-images`) | RHOAI images from before the move to `quay.io/rhoai` | Former build process | **Legacy**, kept for supported 2.x releases |
| [`quay.io/opendatahub/workbench-images`](https://quay.io/repository/opendatahub/workbench-images) | Old aggregate repository; all ODH images as tags of one repository | Former OpenShift CI build | **Legacy**, no longer updated |
| [`quay.io/opendatahub/notebooks`](https://quay.io/repository/opendatahub/notebooks) | Earliest ODH notebook images | Early build process | **Legacy**, no longer referenced |
| [`quay.io/opendatahub-contrib/workbench-images`](https://quay.io/repository/opendatahub-contrib/workbench-images) | Community workbench images | [opendatahub-io-contrib/workbench-images](https://github.com/opendatahub-io-contrib/workbench-images) | Separate project, not built from this repo |

## How the repositories relate

```text
ODH (opendatahub-io/notebooks, this repo)

  opendatahub-io/base-containers
    └─> quay.io/opendatahub/odh-midstream-*              (midstream bases)
          └─> base-images/  (.tekton/odh-base-image-*-push.yaml)
                └─> quay.io/opendatahub/odh-base-image-*-py312-c9s
                      └─> build-args/<variant>.conf  (BASE_IMAGE)
                            └─> quay.io/opendatahub/odh-workbench-*-py312-{ubi9,c9s}
                                quay.io/opendatahub/odh-pipeline-runtime-*-py312-{ubi9,c9s}
                                  └─> manifests/odh/base/params*.env  → ODH ImageStreams

RHOAI (red-hat-data-services/notebooks, downstream)

  AIPCC
    └─> quay.io/aipcc/base-images/*-el9.8                (RHEL 9 bases)
          └─> build-args/konflux.<variant>.conf  (BASE_IMAGE)
                └─> quay.io/rhoai/odh-workbench-*-rhel9
                    quay.io/rhoai/odh-pipeline-runtime-*-rhel9
                      └─> release → registry.redhat.io/rhoai/*-rhel9
                            └─> manifests/rhoai/base/params.env  → RHOAI ImageStreams
```

`PRODUCT` selects which side of this diagram a local build follows; see
[ARCHITECTURE.md](../ARCHITECTURE.md#build-system).

## Active repositories

### `quay.io/opendatahub` (ODH)

Each ODH image has its own repository, named after its Konflux component, for example
[`quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9`](https://quay.io/repository/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9?tab=tags)
or
[`quay.io/opendatahub/odh-pipeline-runtime-datascience-cpu-py312-ubi9`](https://quay.io/repository/opendatahub/odh-pipeline-runtime-datascience-cpu-py312-ubi9?tab=tags).
The [README image inventory](../README.md#image-inventory-list) links the main ones;
`.tekton/` has the complete list.

Tags written by the pipelines in [`.tekton/`](../.tekton/README-odh.md):

- `main` push builds: `{{revision}}` (the commit SHA) and `main-{{revision}}`.
- `stable` push builds (`-ci` components): `odh-stable` plus a release tag such as `3.6-v1.50`.
- Pull-request builds: `on-pr-{{revision}}` (or `odh-pr`), most with a 5-day expiry.

The ODH base images (`odh-base-image-cpu-py312-c9s`, `odh-base-image-cuda-py312-c9s`,
`odh-base-image-rocm-py312-c9s`) are built from [`base-images/`](../base-images/README.md)
and are the `BASE_IMAGE` for ODH workbench builds. The CUDA and ROCm bases in turn start
from the `quay.io/opendatahub/odh-midstream-*` images built in
[opendatahub-io/base-containers](https://github.com/opendatahub-io/base-containers).

### `quay.io/rhoai` (RHOAI)

RHOAI images are built by Konflux from the downstream
[red-hat-data-services/notebooks](https://github.com/red-hat-data-services/notebooks)
repository (see [docs/bodies-of-water.md](bodies-of-water.md) for how code gets there).
Each image has its own repository with a `-rhel9` suffix, for example
`quay.io/rhoai/odh-workbench-jupyter-datascience-cpu-py312-rhel9` or
`quay.io/rhoai/odh-pipeline-runtime-datascience-cpu-py312-rhel9`. Tags follow the
release branch (e.g. `rhoai-3.5`, `rhoai-3.5-<sha>`, `rhoai-3.5-nightly`); see
[docs/code-flow-odh-to-rhoai.md](code-flow-odh-to-rhoai.md) for the full tag scheme.

`quay.io/rhoai` holds development, nightly, and release-candidate builds. Released images
are promoted to `registry.redhat.io/rhoai/`, which is what
[`manifests/rhoai/base/params.env`](../manifests/rhoai/base/params.env) references.
Most `quay.io/rhoai` repositories require Red Hat credentials to pull.

### `quay.io/aipcc/base-images` (RHOAI bases)

RHOAI builds start from RHEL 9 base images published by AIPCC, for example
`quay.io/aipcc/base-images/cpu-torch2.13-el9.8` or
`quay.io/aipcc/base-images/cuda13.0-torch2.13-el9.8`. They are referenced by digest
from `build-args/konflux.<variant>.conf`. Repository names change with accelerator and
RHEL versions, so check the `.conf` files for the current set. See
[docs/subscribed-builds.md](subscribed-builds.md) for pulling them locally.

## Legacy repositories

Do not use these for new defaults, tests, or documentation when an active repository
exists.

- **`quay.io/opendatahub/workbench-images`**: one repository with every ODH image as a
  tag (e.g. `jupyter-minimal-ubi9-python-3.9-2024a-20240317-6f4c36b`). It was filled by
  the former OpenShift CI build and stopped receiving new images when `main` moved to
  Konflux. Older examples in this repository may still point at it.
- **`quay.io/modh`**: older RHOAI images, including `quay.io/modh/runtime-images` and
  per-image repositories such as `quay.io/modh/odh-pipeline-runtime-*`. Current RHOAI
  builds go to `quay.io/rhoai` instead. Keep `quay.io/modh` available: it may still be
  needed for patch releases of supported RHOAI 2.x versions. Tests treat `quay.io/modh`
  references as pre-Konflux images without SBOMs.
- **`quay.io/opendatahub/notebooks`**: the first ODH notebook images. The ImageStream
  manifests stopped referencing it in 2024.

## Other organizations

- **`quay.io/opendatahub-contrib/workbench-images`**: community-maintained workbench
  images from
  [opendatahub-io-contrib/workbench-images](https://github.com/opendatahub-io-contrib/workbench-images).
  This repository does not build or publish them.
