# Patches Directory

This directory contains modified files from the `prefetch-input/code-server` submodule and its nested submodules. Patched files are applied in the Dockerfile so the submodule can stay in its original state while we get better layer caching.

## Patch rationale (original vs patched)

See **[PATCHES.md](./PATCHES.md)** for a side-by-side comparison of each patched file with the original and the reason for each change.

## Structure

Patches live under `patches/code-server/` and are copied onto `prefetch-input/code-server/` by the Dockerfile (e.g. `patches/code-server/ci/build-scripts/*.sh` → `prefetch-input/code-server/ci/build/*.sh`). The Dockerfile uses `${CODESERVER_SOURCE_CODE}` which already includes the prefetch path.

## Cachi2

Run Cachi2 **with the patched files applied** (e.g. apply patches before Cachi2, or point Cachi2 at a repo that already has these changes) so `node-gyp`, `proc-log`, and pinned `tslib` are prefetched. Otherwise the image build can fail with ENOTCACHED or MODULE_NOT_FOUND when native modules’ install scripts run.

## How to Update Patches

1. Make changes to files in `prefetch-input/code-server/` as needed (e.g. under `ci/build/`).
2. Copy the modified files into `patches/code-server/` using the paths the Dockerfile expects (e.g. `ci/build/*.sh` → `patches/code-server/ci/build-scripts/*.sh`):
   ```bash
   cp prefetch-input/code-server/ci/build/build-release.sh \
      patches/code-server/ci/build-scripts/build-release.sh
   ```
3. Reset the code-server submodule to its original state:
   ```bash
   cd prefetch-input/code-server
   git checkout HEAD -- .
   cd ../..
   ```
4. The Dockerfile will automatically apply patches from the `patches/` directory

## Resetting the Code-Server Submodule

To reset the code-server submodule back to its original checked-out state:

```bash
cd prefetch-input/code-server
git checkout HEAD -- .
cd ../..
```

This will discard any local modifications and restore the files to their original state from the repository.
