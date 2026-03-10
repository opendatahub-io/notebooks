# Code - Extensions

Our code-server image will provide an easy way for users to deploy a code instance with AI focused extensions.

All extensions can be downloaded from either [https://open-vsx.org](https://open-vsx.org) (preferred) or [https://marketplace.visualstudio.com](https://marketplace.visualstudio.com)

> Detail: some extensions are already available inside of other extensions, that are called "extension packages", i.e., when you install the `ms-python.python` extension, it already comes bundled with the `ms-python.debugpy` extension.
>
> All extension files are available inside the `ubiX-python-Y/utils/` directory, but only the main ones will be installed.

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

To update the extensions, we suggest running a code-server image locally using Podman and manually checking the extensions tab, in a way that you can identify the version available to the version of code-server that you are running on, since some extensions are not available to some code-server versions.

1. Run a code-server image
2. Search for the desired extensions on the `extensions` tab
3. Search for the desired version of the extension that you want to install
4. Under `Resources`, you can click on `Marketplace` to see more details on `Open VSX Registry`
  1. On `Open VSX Registry` you can select a specific version or click on `Download` to download the `vsix` file

## Git LFS integration

Extension packages (`.vsix` files) vendored into this repository are automatically managed by Git LFS via `.gitattributes` rules (`*.vsix filter=lfs diff=lfs merge=lfs -text`). You don't need to manually run `git lfs track` for new `.vsix` files.

When adding or updating extensions, place the downloaded `.vsix` artifacts under the appropriate `codeserver/ubiX-python-Y/utils/` directory. Commit them normally; they will be stored as LFS objects.

### Current versions

For `codeserver/ubi9-python-3.12`, the image expects these `.vsix` files in `utils/`:

- **ms-python.python** 2026.0.0: <https://open-vsx.org/api/ms-python/python/2026.0.0/file/ms-python.python-2026.0.0.vsix>
- **ms-toolsai.jupyter** 2025.9.1: <https://open-vsx.org/api/ms-toolsai/jupyter/2025.9.1/file/ms-toolsai.jupyter-2025.9.1.vsix>

Download with `curl -o <filename> <url>` and place under `codeserver/ubi9-python-3.12/utils/`.

## Troubleshooting

- If you see errors like "End of central directory record signature not found" when installing `.vsix` files, it usually means LFS pointers were checked out instead of the actual binaries.
  - For local development: run `git lfs install` once, then `git lfs pull` to fetch LFS content.
  - For CI or other environments: ensure the Git checkout step enables LFS, or run `git lfs pull` after checkout.
