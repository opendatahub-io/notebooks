# Mongocli: submodule + Hermeto/Cachi2 (Konflux hermetic build)

This image builds **mongocli** from source for FIPS compliance, without downloading the source at build time (ProdSec/Conforma compliant).

## Submodule location

The mongocli source lives at the **repository root**:

**`prefetch-input/mongocli`**

It is a git submodule (see `.gitmodules`). Jupyter `prefetch-input` symlinks under `jupyter/*/ubi9-python-3.12/` point at this tree. The pattern matches `codeserver/.../prefetch-input/code-server` (component-local submodule), except mongocli is shared at the repo root.

## First-time clone (for new clones of this repo)

From the **repository root**:

```bash
git submodule update --init --recursive prefetch-input/mongocli
cd prefetch-input/mongocli
git checkout mongocli/v2.0.4
cd ../..
```

## Updating the pinned version

```bash
cd prefetch-input/mongocli
git fetch origin && git checkout mongocli/vX.Y.Z
cd ../..
git add prefetch-input/mongocli
git commit -m "Bump mongocli submodule to vX.Y.Z"
```

## How it works

- **Tekton** (`.tekton/odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312-ubi9-*.yaml` and datascience pipelines that build mongocli):
  - `hermetic: "true"` so the build has no network access.
  - `prefetch-input` includes `type: gomod` for `path: prefetch-input/mongocli`. Cachi2/Hermeto prefetches Go modules for that path and makes them available to the build.

- **Dockerfile.cuda** (and related):
  - `COPY prefetch-input/mongocli` into the builder stage (no `curl`/download).
  - Sources `/cachi2/env` when present (Konflux injects this so `go build` uses the prefetched module cache).
  - Builds with `-tags strictfipsruntime` for FIPS.

Ensure the Konflux **clone** step fetches submodules so `prefetch-input/mongocli` is populated in the build context.
