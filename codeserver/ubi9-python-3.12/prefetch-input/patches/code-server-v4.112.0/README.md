# code-server v4.112.0 build overlay

Files here are **copied on top of** the `prefetch-input/code-server` git submodule
during the hermetic build (before `apply-patch.sh` runs). They pin npm lockfiles,
patch VS Code build scripts, and adjust postinstall behaviour for offline and
GHA builds.

Do not edit the submodule directly for release-specific changes — keep overrides
in this directory so the submodule can be updated independently.

## What is overridden

| Path | Why |
| ---- | --- |
| `ci/dev/postinstall.sh` | Hermetic offline `npm ci`; GHA `--ignore-scripts` follow-up for ripgrep, spdlog, node-pty |
| `ci/build/build-vscode.sh` | VS Code compile settings for hermetic build |
| `custom-packages/` | Lockfiles for code-server custom npm packages |
| `lib/vscode/` (partial) | Pinned `package.json` / `package-lock.json`, build script patches (`gulpfile.reh.ts`, `extensions.ts`, `preinstall.ts`, …) |
| `test/` | Test tree lockfiles included in npm prefetch |
| `ripgrep/postinstall.js` | Install ripgrep from prefetched RH wheel instead of downloading |
| `agent-browser/postinstall.js` | Offline agent-browser install |

Upstream code-server `.patch` files under the submodule's `patches/` directory are
still applied via `patches/series` in `apply-patch.sh`.

## Bumping code-server / VS Code

1. Update the submodule pointer in `.gitmodules` / `prefetch-input/code-server`.
2. Copy this directory to `code-server-vX.Y.Z/` (or rename in place) and refresh
   overridden lockfiles from the new submodule baseline.
3. Update `CODESERVER_VERSION` in `Dockerfile.konflux.cpu` and Tekton params.
4. Regenerate npm prefetch — commit updated `package-lock.json` files under this
   overlay **and** re-run npm download:
   ```bash
   ./scripts/lockfile-generators/download-npm.sh \
     --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-pull-request.yaml
   ```
5. Re-run full prefetch and verify the image builds on amd64 (Konflux) and GHA:
   ```bash
   RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/amd64 \
     ./scripts/lockfile-generators/prefetch-all.sh \
       --component-dir codeserver/ubi9-python-3.12 --rhds
   gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/amd64 PUSH_IMAGES=no
   ```
6. Update extension versions in [`../../../Extensions.md`](../../../Extensions.md)
   and built-in `.vsix` paths in `utils/` if VS Code built-ins changed.

## Regenerating npm lockfiles in this overlay

When you change `package.json` under this tree:

1. Edit against a checkout of the submodule (or copy changed files here).
2. Run `npm ci` / `npm install` in the relevant subdirectory with network access.
3. Copy resulting `package-lock.json` files back into this overlay path.
4. Re-run `download-npm.sh` (see above) and commit both lockfiles and Tekton-prefetched
   npm cache is **not** committed — only lockfiles and overlay sources.

Python/RPM lock regeneration is documented in
[`../../README.md`](../../README.md) and the repo
[`scripts/lockfile-generators/README.md`](../../../../../scripts/lockfile-generators/README.md).
