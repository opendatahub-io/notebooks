# Contributing Guidelines

Thanks for your interest in contributing to the `notebooks` repository.

### Is this your first contribution?

Please take a few minutes to read GitHub's guide on [How to Contribute to Open Source](https://opensource.guide/how-to-contribute/).
It's a quick read, and it's a great way to introduce yourself to how things work behind the scenes in open-source projects.

### We actively welcome your pull requests!

If you want to update the documentation, [README.md](README.md) is the file you're looking for.

Pull requests are the best way to propose changes to the notebooks repository:

- Configure name and email in git
- Fork the repo and create your branch from main.
- Sign off your commit using the -s, --signoff option. Write a good commit message (see [How to Write a Git Commit Message](https://chris.beams.io/posts/git-commit/))
- If you've added code that should be tested, [add tests](https://github.com/openshift/release/blob/master/ci-operator/config/opendatahub-io/notebooks/opendatahub-io-notebooks-main.yaml).
- Ensure the test suite passes.
- Make sure your code lints.
- Issue that pull request!

### Some basic instructions to create a new notebook

- Decide from which notebook you want to derive the new notebook
- Create a proper filepath and naming to the corresponding folder
- Add the minimum files you have to add:
    - Pipfile with the additional packages
    - Dockefile with proper instructions
    - Kustomization objects to deploy the new notebook into an openshift cluster (Kustomization.yaml, service.yaml, statefulset.yaml)
- Create instructions into Makefile, for example if you derive the new notebooks from minimal then the recipe should be like the following:
    ```
    # Your comment here
    .PHONY: jupyter-${NOTEBOOK_NAME}-ubi8-python-3.8
    jupyter-${NOTEBOOK_NAME}-ubi8-python-3.8: jupyter-minimal-ubi8-python-3.8
	$(call image,$@,jupyter/${NOTEBOOK_NAME}/ubi8-python-3.8,$<)
    ```
- Add the paths of the new pipfiles under `refresh-pipfilelock-files`
- Run the [piplock-renewal.yaml](https://github.com/opendatahub-io/notebooks/blob/main/.github/workflows/piplock-renewal.yaml) against your fork branch, check [here](https://github.com/opendatahub-io/notebooks/blob/main/README.md) for more info.
- Test the changes locally, by manually running the `$ make jupyter-${NOTEBOOK_NAME}-ubi8-python-3.8` from the terminal.

### Working with linters

- Run pre-commit before you commit, to lint the Python sources that have been put under its management
    ```
    uv run pre-commit run --all-files
    ```
- If you like, you can install pre-commit to run automatically using `uv run pre-commit install`, as per its [install instructions](https://pre-commit.com/#3-install-the-git-hook-scripts)

### Some basic instructions how to apply the new tests into [openshift-ci](https://github.com/openshift/release)

- Fork the [openshift-ci](https://github.com/openshift/release) repo and create your branch from master.
  - Definition and configuration of jobs used by this repository is on these places:
    - [jobs](https://github.com/openshift/release/tree/master/ci-operator/jobs/opendatahub-io/notebooks)
    - [config](https://github.com/openshift/release/tree/master/ci-operator/config/opendatahub-io/notebooks)
- Issue a pull request there by adding the following.
- Get navigated into [opendatahub-io-notebooks-main.yaml](https://github.com/openshift/release/blob/master/ci-operator/config/opendatahub-io/notebooks/opendatahub-io-notebooks-main.yaml) file.
  - Under `images` option, add build instructions (directory path, from(parent image) and to(new notebook name))
  - Under `tests` option, add the tests (*notebook-jupyter-${NOTEBOOK_NAME}-ubi8-python-3-8-image-mirror* and *notebook-jupyter-${NOTEBOOK_NAME}-ubi8-python-3-8-pr-image-mirror*)
  - Under `notebooks-e2e-tests` add the *jupyter-${NOTEBOOK_NAME}-ubi8-python-3.8-test-e2e*
  - Finally, run on terminal `$make jobs` and ensure that there are not errors.
- Commit your PR


### Testing your PR locally

- Test the changes locally, by manually running the `$make jupyter-${NOTEBOOK_NAME}-ubi8-python-3.8` from the terminal. This definitely helps in that initial phase.

### Working with RHDS and ODH Repositories

When contributing to notebook-related changes in the Red Hat Data Science (RHDS) ecosystem, it's important to understand the repository structure and contribution workflow:

#### Repository Responsibilities

**OpenDataHub Notebooks Repository (`odh/notebooks`)**:
- **Primary Development Location**: All changes to notebook images, dependencies, configurations, and documentation should be made here first
- **What to modify**: Dockerfiles, pyproject.toml files, test suites, documentation, CI/CD configurations, and all notebook-related code
- **Sync Process**: Changes made here are automatically synced to the RHDS notebooks repository

**RHDS Notebooks Repository (`rhds/notebooks`)**:
- **Limited Changes**: Only `Dockerfile.konflux` files should be modified directly in this repository. Changes to these files flow to RHOAI upcoming release
- **Konflux Integration**: This repository contains Konflux-specific build configurations and pipeline definitions
- **Automated Sync**: Receives updates from the ODH notebooks repository automatically

#### Contribution Workflow

1. **For General Changes**:
   - Make all notebook-related changes in `odh/notebooks` and they will be automatically synchronized to `rhds/notebooks`
   - Submit pull requests to the OpenDataHub repository
   - Changes to everything except `Dockerfile.konflux` files should be done in `odh/notebooks` and synced to `rhds/notebooks`

2. **For Konflux-Specific Changes** (Requires Special Attention):
   - Modify `Dockerfile.konflux` files directly in `rhds/notebooks`
   - These files contain Konflux build configurations and require special attention in the downstream repository
   - Changes to these files flow to RHOAI upcoming release and need careful coordination

3. **For Tekton Pipeline Changes**:
   - Modify Tekton pipelines in the central repository as specified in the specific README documentation
   - Follow the centralized pipeline management guidelines

#### Best Practices

- **Always start with ODH**: Begin your contributions in the OpenDataHub notebooks repository unless specifically working on Konflux configurations
- **Check synchronization**: Verify that your changes are properly synchronized between repositories
- **Follow documentation**: Refer to repository-specific README files for detailed contribution guidelines
- **Coordinate changes**: When making related changes across repositories, ensure consistency and proper sequencing

This workflow ensures that the OpenDataHub community remains the primary development hub while maintaining compatibility with Red Hat's enterprise tooling and processes.

### Review and Merge Process

- Once the PR is submitted, you can either select specific reviewers or let the bot to select reviewers [automatically](https://prow.ci.openshift.org/plugins?repo=opendatahub-io%2Fnotebooks).
- For the PR to be merged, it must receive 2 reviews from the repository [approvals/reviewers](/OWNERS). Following that, an `/approve` comment must be added by someone with approval rights. If the author of the PR has approval rights, it is preferred that they perform the merge action.
