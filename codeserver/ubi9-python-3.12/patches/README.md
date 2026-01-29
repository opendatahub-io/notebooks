# Patches Directory

This directory contains modified files from the `prefetch-input/code-server` submodule and its nested submodules.

## Purpose

By separating modified files into this `patches/` directory, we can:
1. Keep the `prefetch-input/code-server` submodule in its original checked-out state
2. Apply patches separately in the Dockerfile, allowing better Docker layer caching
3. Avoid invalidating cached layers when only patched files change

## Structure

The patches directory mirrors the structure of the code-server directory (relative to prefetch-input):
```
patches/
└── code-server/
    └── ci/
        └── build/
            ├── build-release.sh
            └── build-standalone-release.sh
```

Note: The path is `patches/code-server/` (not `patches/prefetch-input/code-server/`) because
the Dockerfile uses `${CODESERVER_SOURCE_CODE}` which already includes the `prefetch-input/` path.

## Current Patches

### `prefetch-input/code-server/ci/build/build-release.sh`
- **Changes**: Added `fix_shrinkwrap_paths()` function to fix npm registry URLs and relative paths in `npm-shrinkwrap.json` files
- **Purpose**: Ensures offline npm installs work correctly by converting registry URLs to `file:///cachi2` paths

### `prefetch-input/code-server/ci/build/build-standalone-release.sh`
- **Changes**: Added `fix_shrinkwrap_paths()` function and logic to fix shrinkwrap files in the standalone release directory
- **Purpose**: Ensures offline npm installs work correctly during standalone release builds

## How to Update Patches

1. Make changes to files in `prefetch-input/code-server/` as needed
2. Copy the modified files to `patches/` maintaining the same directory structure:
   ```bash
   cp prefetch-input/code-server/ci/build/build-release.sh \
      patches/code-server/ci/build/build-release.sh
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
