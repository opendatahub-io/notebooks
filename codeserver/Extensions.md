# Code - Extensions

Our code-server image provides VS Code in the browser with AI-focused extensions
for OpenShift AI workbenches. Builds are **hermetic** — see
[`ubi9-python-3.12/README.md`](ubi9-python-3.12/README.md).

All extensions can be downloaded from either [https://open-vsx.org](https://open-vsx.org) (preferred) or [https://marketplace.visualstudio.com](https://marketplace.visualstudio.com)

> Detail: some extensions are already available inside of other extensions, that are called "extension packages", i.e., when you install the `ms-python.python` extension, it already comes bundled with the `ms-python.debugpy` extension.
>
> **User-facing** extension `.vsix` files live in `codeserver/ubi9-python-3.12/utils/` and are installed at image build time.
> **Built-in** VS Code debugger `.vsix` files in the same directory are consumed by the hermetic build via `prefetch-input/patches/setup-offline-binaries.sh` (not installed through the Dockerfile extension step).

List of extensions used:

_Extensions in the second-order list items are already bundled in the first order list item `vsix` file, no need to install separately._

- Python [[ms-python.python]](https://open-vsx.org/extension/ms-python/python)
  - Python Debugger [[ms-python.debugpy]](https://open-vsx.org/extension/ms-python/debugpy)
- Jupyter [[ms-toolsai.jupyter]](https://open-vsx.org/extension/ms-toolsai/jupyter)
  - Jupyter Keymap [[ms-toolsai.jupyter-keymap]](https://open-vsx.org/extension/ms-toolsai/jupyter-keymap)
  - Jupyter Notebook Renderers [[ms-toolsai.jupyter-renderers]](https://open-vsx.org/extension/ms-toolsai/jupyter-renderers)
  - Jupyter Cell Tags [[ms-toolsai.vscode-jupyter-cell-tags]](https://open-vsx.org/extension/ms-toolsai/vscode-jupyter-cell-tags)
  - Jupyter Slide Show [[ms-toolsai.vscode-jupyter-slideshow]](https://open-vsx.org/extension/ms-toolsai/vscode-jupyter-slideshow)

## Prerequisites

- git-lfs (required to handle `.vsix` extension files stored in this repository)

## Update process

To update extensions after a code-server version bump, follow the checklist in
[`prefetch-input/patches/code-server-v4.112.0/README.md`](ubi9-python-3.12/prefetch-input/patches/code-server-v4.112.0/README.md).

For ad-hoc version checks:

1. Run a code-server image
2. Search for the desired extensions on the `extensions` tab
3. Search for the desired version of the extension that you want to install
4. Under `Resources`, you can click on `Marketplace` to see more details on `Open VSX Registry`
  1. On `Open VSX Registry` you can select a specific version or click on `Download` to download the `vsix` file

## Git LFS integration

Extension packages (`.vsix` files) vendored into this repository are automatically managed by Git LFS via `.gitattributes` rules (`*.vsix filter=lfs diff=lfs merge=lfs -text`). You don't need to manually run `git lfs track` for new `.vsix` files.

When adding or updating extensions, place the downloaded `.vsix` artifacts under
`codeserver/ubi9-python-3.12/utils/`. Commit them normally; they will be stored as LFS objects.

If you add URLs to `prefetch-input/rhds/artifacts.in.yaml`, regenerate the artifact lock:

```bash
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
  --artifact-input codeserver/ubi9-python-3.12/prefetch-input/rhds/artifacts.in.yaml
```

### Current versions

For `codeserver/ubi9-python-3.12` (code-server v4.112.0 / VS Code 1.112.0), the image expects these user-facing `.vsix` files in `utils/`:

- **ms-python.python** 2026.4.0: <https://open-vsx.org/api/ms-python/python/2026.4.0/file/ms-python.python-2026.4.0.vsix>
- **ms-toolsai.jupyter** 2025.9.1 (latest on Open VSX): <https://open-vsx.org/api/ms-toolsai/jupyter/2025.9.1/file/ms-toolsai.jupyter-2025.9.1.vsix>

The same `utils/` directory also holds built-in VS Code extensions used during the hermetic code-server build. Those are not installed via `Dockerfile.konflux.cpu`; they are consumed by `prefetch-input/patches/setup-offline-binaries.sh`:

- **ms-vscode.js-debug** 1.112.0 (matches VS Code 1.112 built-in)
- **ms-vscode.js-debug-companion** 1.1.3
- **ms-vscode.vscode-js-profile-table** 1.0.10

Download with `curl -o <filename> <url>` and place under `codeserver/ubi9-python-3.12/utils/`.

## Troubleshooting

- If you see errors like "End of central directory record signature not found" when installing `.vsix` files, it usually means LFS pointers were checked out instead of the actual binaries.
  - For local development: run `git lfs install` once, then `git lfs pull` to fetch LFS content.
  - For CI or other environments: ensure the Git checkout step enables LFS, or run `git lfs pull` after checkout.
