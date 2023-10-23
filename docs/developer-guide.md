The following sections are aimed to provide a comprehensive guide for developers, enabling them to understand the project's architecture and seamlessly contribute to its development.

## Getting Started
This project utilizes three branches for the development: the **main** branch, which hosts the latest development, and t**wo additional branches for each release**.
These release branches follow a specific naming format: YYYYx, where "YYYY" represents the year, and "x" is an increasing letter. Thus, they help to keep working on minor updates and bug fixes on the supported versions (N & N-1) of each workbench.

## Architecture
The structure of the notebook's build chain is derived from the parent image. To better comprehend this concept, refer to the following graph.

<p align="center">
<img src="https://github.com/opendatahub-io/notebooks/assets/42587738/9e5df03f-01f4-4bba-9792-3b56e9b5b912" data-canonical-src="https://github.com/opendatahub-io/notebooks/assets/42587738/9e5df03f-01f4-4bba-9792-3b56e9b5b912" width="820" height="450" />
</p>


Each notebook inherits the properties of its parent. For instance, the TrustyAI notebook inherits all the installed packages from the Standard Data Science notebook, which in turn inherits the characteristics from its parent, the Minimal notebook.

Detailed instructions on how developers can contribute to this project can be found in the [contribution.md](https://github.com/opendatahub-io/notebooks/blob/main/CONTRIBUTING.md#some-basic-instructions-to-create-a-new-notebook) file.

## Workbench ImageStreams

ODH supports multiple out-of-the-box pre-built workbench images ([provided in this repository](https://github.com/opendatahub-io/notebooks)). For each of those workbench images, there is a dedicated ImageStream object definition. This ImageStream object references the actual image tag(s) and contains additional metadata that describe the workbench image.

### **Annotations**

Aside from the general ImageStream config values, there are additional annotations that can be provided in the workbench ImageStream definition. This additional data is leveraged further by the [odh-dashboard](https://github.com/opendatahub-io/odh-dashboard/).

### **ImageStream-specific annotations**
The following labels and annotations are specific to the particular workbench image. They are provided in their respective sections in the `metadata` section.
```yaml
metadata:
  labels:
    ...
  annotations:
    ...
```
### **Available labels**
-  **`opendatahub.io/notebook-image:`** - a flag that determines whether the ImageStream references a workbench image that is meant be shown in the UI
### **Available annotations**
- **`opendatahub.io/notebook-image-url:`** - a URL reference to the source of the particular workbench image
- **`opendatahub.io/notebook-image-name:`** - a desired display name string for the particular workbench image (used in the UI)
- **`opendatahub.io/notebook-image-desc:`** - a desired description string of the of the particular workbench image (used in the UI)
- **`opendatahub.io/notebook-image-order:`** - an index value for the particular workbench ImageStream (used by the UI to list available workbench images in a specific order)
- **`opendatahub.io/recommended-accelerators`** - a string that represents the list of recommended hardware accelerators for the particular workbench ImageStream (used in the UI)

### **Tag-specific annotations**
One ImageStream can reference multiple image tags. The following annotations are specific to a particular workbench image tag and are provided in its `annotations:` section.
```yaml
spec:
  tags:
    - annotations:
        ...
      from:
        kind: DockerImage
        name: image-repository/tag
      name: tag-name
```
### **Available annotations**
  - **`opendatahub.io/notebook-software:`** - a string that represents the technology stack included within the workbench image. Each technology in the list is described by its name and the version used (e.g. `'[{"name":"CUDA","version":"11.8"},{"name":"Python","version":"v3.9"}]`')
  - **`opendatahub.io/notebook-python-dependencies:`** -  a string that represents the list of Python libraries included within the workbench image. Each library is described by its name and currently used version (e.g. `'[{"name":"Numpy","version":"1.24"},{"name":"Pandas","version":"1.5"}]'`)
  - **`openshift.io/imported-from:`** - a reference to the image repository where the workbench image was obtained (e.g. `quay.io/repository/opendatahub/workbench-images`)
  - **`opendatahub.io/workbench-image-recommended:`** - a flag that allows the ImageStream tag to be marked as Recommended (used by the UI to distinguish which tags are recommended for use, e.g., when the workbench image offers multiple tags to choose from)

### **ImageStream definitions for the supported out-of-the-box images in ODH**

The ImageStream definitions of the out-of-the-box workbench images for ODH can be found [here](https://github.com/opendatahub-io/notebooks/tree/main/manifests).

### **Example ImageStream object definition**

An exemplary, non-functioning ImageStream object definition that uses all the aforementioned annotations is provided below.

```yaml
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  labels:
    opendatahub.io/notebook-image: "true"
  annotations:
    opendatahub.io/notebook-image-url: "https://github.com/example-workbench-source-repository/tree/path-to-source"
    opendatahub.io/notebook-image-name: "Example Jupyter Notebook"
    opendatahub.io/notebook-image-desc: "Exemplary Jupyter notebook image just for demonstrative purposes"
    opendatahub.io/notebook-image-order: "1"
    opendatahub.io/recommended-accelerators: '["nvidia.com/gpu", "habana.com/gen1"]'
  name: example-jupyter-notebook
spec:
  lookupPolicy:
    local: true
  tags:
  - annotations:
      opendatahub.io/notebook-software: '[{"name":"Python","version":"v3.9"}]'
      opendatahub.io/notebook-python-dependencies: '[{"name":"Boto3","version":"1.26"},{"name":"Kafka-Python","version":"2.0"},{"name":"Kfp-tekton","version":"1.5"},{"name":"Matplotlib","version":"3.6"},{"name":"Numpy","version":"1.24"},{"name":"Pandas","version":"1.5"},{"name":"Scikit-learn","version":"1.2"},{"name":"Scipy","version":"1.10"}]'
      openshift.io/imported-from: quay.io/opendatahub/workbench-images
      opendatahub.io/workbench-image-recommended: 'true'
    from:
      kind: DockerImage
      name: quay.io/opendatahub/workbench-images@sha256:value-of-the-image-tag
    name: example-tag-name
    referencePolicy:
      type: Source
```

## Continuous Integration
This repository has been added to the[ Openshift CI](https://github.com/openshift/release/blob/master/ci-operator/config/opendatahub-io/notebooks/opendatahub-io-notebooks-main.yaml) to build the different notebooks using the flow described in the Container Image Layering section. Every notebook will use a previous notebook as the base image:

```
images:
  - context_dir: ${NOTEBOOK_DIR}
    dockerfile_path: Dockerfile
    from: ${NOTEBOOK_BASE_IMAGE_NAME}
    to: ${NOTEBOOK_IMAGE_NAME}
```
The opendatahub-io-ci-image-mirror job will be used to mirror the images from the Openshift CI internal registry to the ODH Quay repository.

```
tests:
  - as: ${NOTEBOOK_IMAGE_NAME}-image-mirror
    steps:
      dependencies:
          SOURCE_IMAGE_REF: ${NOTEBOOK_IMAGE_NAME}
      env:
          IMAGE_REPO: notebooks
      workflow: opendatahub-io-ci-image-mirror
```
The images mirrored under 2 different scenarios:
1. A new PR is opened.
1. A PR is merged.

The Openshift CI is also configured to run the unit and integration tests:

```
tests:
  - as: notebooks-e2e-tests
    steps:
      test:
        - as: ${NOTEBOOK_IMAGE_NAME}-e2e-tests
          commands: |
            make test
          from: src
```

## GitHub Actions
This section provides an overview of the automation functionalities.

### **Piplock Renewal** [[Link]](https://github.com/opendatahub-io/notebooks/blob/main/.github/workflows/piplock-renewal-2023a.yml)

This GitHub action is configured to be triggered on a weekly basis, specifically every Monday at 22:00 PM UTC. Its main objective is to automatically update the Pipfile.lock files by fetching the most recent minor versions available. Additionally, it also updates the hashes for the downloaded files of Python dependencies, including any sub-dependencies. Once the updated files are pushed, the CI pipeline is triggered to generate new updated images based on these changes.

### **Sync the downstream release branch with the upstream** [[Link]](https://github.com/red-hat-data-services/notebooks/blob/main/.github/workflows/sync-release-branch-2023a.yml)

This GitHub action is configured to be triggered on a weekly basis, specifically every Tuesday at 08:00 AM UTC. Its main objective is to automatically update the downstream release branch with the upstream branch.

### **Digest Updater workflow on the manifests** [[Link]](https://github.com/opendatahub-io/odh-manifests/blob/master/.github/workflows/notebooks-digest-updater-upstream.yaml)

This GitHub action is designed to be triggered on a weekly basis, specifically every Friday at 12:00 AM UTC. Its primary purpose is to automate the process of updating the SHA digest of the notebooks. It achieves this by fetching the new SHA values from the quay.io registry and updating the [param.env](https://github.com/opendatahub-io/odh-manifests/blob/master/notebook-images/base/params.env) file, which is hosted on the odh-manifest repository. By automatically updating the SHA digest, this action ensures that the notebooks remain synchronized with the latest changes.

### **Digest Updater workflow on the live-builder** [[Link]](https://gitlab.cee.redhat.com/data-hub/rhods-live-builder/-/blob/main/.gitlab/notebook-sha-digest-updater.yml)

This GitHub action works with the same logic as the above and is designed to be triggered on a weekly basis, specifically every Friday. It is also update the SHA digest of the images into the [CSV](https://gitlab.cee.redhat.com/data-hub/rhods-live-builder/-/blob/main/rhods-operator-live/bundle/template/manifests/clusterserviceversion.yml.j2#L725) file on the live-builder repo.


[Previous Page](https://github.com/opendatahub-io/notebooks/wiki/Workbenches) | [Next Page](https://github.com/opendatahub-io/notebooks/wiki/User-Guide)
