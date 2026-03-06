# Mongocli: submodule + Hermeto/Cachi2 (Konflux hermetic build)

This image builds **mongocli** from source for FIPS compliance, without downloading the source at build time (ProdSec/Conforma compliant).

## Submodule location

The mongocli source lives at:

**`jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli`**

It is added as a git submodule (see `.gitmodules`). Same pattern as `codeserver/.../prefetch-input/code-server`.

## First-time clone (for new clones of this repo)

From the **repository root**:

```bash
git submodule update --init --recursive jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
cd jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
git checkout mongocli/v2.0.4
cd ../../../../../..
```

## Updating the pinned version

```bash
cd jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
git fetch origin && git checkout mongocli/vX.Y.Z
cd ../../../../../..
git add jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli
git commit -m "Bump mongocli submodule to vX.Y.Z"
```

## How it works

- **Tekton** (`.tekton/odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312-ubi9-*.yaml`):
  - `hermetic: "true"` so the build has no network access.
  - `prefetch-input` includes `type: gomod` for `path: jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli`. Cachi2/Hermeto prefetches Go modules for that path and makes them available to the build.

- **Dockerfile.cuda**:
  - `COPY` the mongocli source from the repo (submodule) into the builder stage (no `curl`/download).
  - Sources `/cachi2/env` when present (Konflux injects this so `go build` uses the prefetched module cache).
  - Builds with `-tags strictfipsruntime` for FIPS.

Ensure the Konflux **clone** step fetches submodules so `jupyter/pytorch+llmcompressor/ubi9-python-3.12/prefetch-input/mongocli` is populated in the build context.
