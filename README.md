# OpenDataHub Notebooks

[![GitHub Tag](https://img.shields.io/github/v/tag/opendatahub-io/notebooks?style=plastic)](https://github.com/opendatahub-io/notebooks/releases)
![GitHub License](https://img.shields.io/github/license/opendatahub-io/notebooks)


Welcome to the OpenDataHub Notebooks repository! This repository provides a collection of notebooks tailored for data analysis, machine learning, research and coding within the OpenDataHub ecosystem. Designed to streamline data science workflows, these notebooks offer an integrated environment equipped with the latest tools and libraries. These notebooks were created to be used with OpenDataHub ecosystem with the ODH Notebook Controller as the launcher.

These workbenches are available at: [quay.io/repository/opendatahub/workbench-images](https://quay.io/repository/opendatahub/workbench-images)

## Getting Started
For a deeper understanding of the architecture underlying this repository, please explore our wiki page [Wiki](https://github.com/opendatahub-io/notebooks/wiki/Workbenches)

### Prerequisites
Make sure the following tools are installed in your environment:
 - podman/docker
 - python
 - pipenv
 - make
 - curl

### Installation
Clone this repository to your local machine:

```shell
git clone https://github.com/opendatahub-io/notebooks.git
cd notebooks
```

### Quick Start Guide

### Build a Notebook

To build a workbench image, you can execute the following command:

```shell
make ${WORKBENCH_NAME} -e  IMAGE_REGISTRY=quay.io/${YOUR_USER}/workbench-images  -e  RELEASE=2023x
```

Using  `IMAGE_REGISTRY` and `RELEASE` variables you can overwrite the default values and use a different registry or release tag

Using `CONTAINER_BUILD_CACHE_ARGS` (default: `--no-cache`), `BUILD_DEPENDENT_IMAGES`, and `PUSH_IMAGES` variables you can further customize the build process.

### Local Execution

The notebook can be run as container on the local systems.

Use podman/docker to execute the workbench images as container.

```shell
podman  run -it -p  8888:8888  quay.io/opendatahub/workbench-images:jupyter-minimal-ubi9-python-3.9-2024a-20240317-6f4c36b
```

### Pipfile.lock Generation

Users can update Pipfile.lock files using the [piplock-renewal.yaml](https://github.com/opendatahub-io/notebooks/blob/main/.github/workflows/piplock-renewal.yaml) GitHub Action. This workflow enables users to specify a target branch for updating and automerging Pipfile.lock files, select the desired Python version for the update as well as to choose whether to include optional directories in the update process. After the action completes, the updated files can be retrieved with a simple git pull.

Note: To ensure the GitHub Action runs successfully, users must add a `GH_ACCESS_TOKEN` secret in their fork.

### Deploy & Test

#### Running Python selftests in Pytest

```shell
pip install poetry
poetry env use /usr/bin/python3.12
poetry config virtualenvs.in-project true
poetry install --sync

poetry run pytest
```

#### Notebooks

Deploy the notebook images in your Kubernetes environment using:
`deploy8-${NOTEBOOK_NAME} for ubi8 or deploy9-${NOTEBOOK_NAME} for ubi9`

```shell
make  deployX-${NOTEBOOK_NAME}
```

Run the test suite against this notebook:

```shell
make  test-${NOTEBOOK_NAME}
```

You can overwrite `NOTEBOOK_REPO_BRANCH_BASE` variable to use a different repository and branch for testing scripts. This is useful when you debug your changes.


```shell
make  test-${NOTEBOOK_NAME} -e  NOTEBOOK_REPO_BRANCH_BASE="https://raw.githubusercontent.com/${YOUR_USER}/notebooks/${YOUR_BRANCH}"
```

Clean up the environment when the tests are finished:

```shell
make  undeployX-${NOTEBOOK_NAME}
```

#### Runtimes

The runtimes image requires to have curl and python installed, so that on runtime additional packages can be installed.

Deploy the runtime images in your Kubernetes environment using: `deploy8-${WORKBENCH_NAME} for ubi8 or deploy9-${WORKBENCH_NAME} for ubi9`

```shell
make  deployX-${WORKBENCH_NAME}
```

Run the validate test suit for checking compatabilty of runtime images:

```shell
make  validate-runtime-image  image=<runtime-image>
```

Clean up the environment when the tests are finished:

```shell
make  undeployX-${WORKBENCH_NAME}
```

## Contributing

Whether you're fixing bugs, adding new notebooks, or improving documentation, your contributions are welcome. Please refer to our [Contribution Guidlines](CONTRIBUTING.md).

## Acknowledgments

A huge thank you to all our contributors and the broader OpenDataHub community!

## License

This project is licensed under  the Apache License 2.0 - see the [LICENSE](https://github.com/opendatahub-io/notebooks/blob/main/LICENSE) file for details.

## Contact

Anything unclear or inaccurate? Please let us know by reporting an issue: [notebooks/issues](https://github.com/opendatahub-io/notebooks/issues/new)
