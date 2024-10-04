# Code - Extensions

Our code-server image will provide an easy way for users to deploy a code instance with AI focused extensions.

All extensions can be downloaded from either [https://open-vsx.org](https://open-vsx.org) (preferred) or [https://marketplace.visualstudio.com](https://marketplace.visualstudio.com)

> Detail: some extensions are already available inside of other extensions, that are called "extension packages", i.e., when you install the `ms-python.python` extension, it already comes bundled with the `ms-python.debugpy` extension.
> 
> All extension files are available inside the `ubiX-python-Y/utils/` directory, but only the main ones will be installed.

List of extensions used:

- Python [ms-python.python]
  - Python Debugger [ms-python.debugpy]
- Jupyter [ms-toolsai.jupyter]
  - Jupyter Keymap [ms-toolsai.jupyter-keymap]
  - Jupyter Notebook Renderers [ms-toolsai.jupyter-renderers]
  - Jupyter Cell Tags [ms-toolsai.vscode-jupyter-cell-tags]
  - Jupyter Slide Show [ms-toolsai.vscode-jupyter-slideshow]

## Update process

To update the extensions, we suggest running a code-server image locally using Podman and manually checking the extensions tab, in a way that you can identify the version available to the version of code-server that you are running on, since some extensions are not available to some code-server versions.

1. Run a code-server image
2. Search for the desired extensions on the `extensions` tab
3. Search for the desired version of the extension that you want to install
4. Under `Resources`, you can click on `Marketplace` to see more details on `Open VSX Registry`
  1. On `Open VSX Registry` you can select a specific version or click on `Download` to download the `vsix` file
