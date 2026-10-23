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
- **`opendatahub.io/notebook-tier:`** - classifies the workbench image for display in the [odh-dashboard](https://github.com/opendatahub-io/odh-dashboard) image selector (workbench creation, pipeline configuration, and related flows). The dashboard reads this value from `metadata.annotations` and shows a tier badge beside each image so users can tell support model and package policy apart before they select an image. Allowed values:
  - **`Red Hat-provided`** — Red Hat–supported images built from the AIPCC (Red Hat Python Index) supply chain. Use when compliance or support requires provenance from the Red Hat curated index rather than unrestricted public PyPI. This is the value used by the out-of-the-box workbench and runtime ImageStreams in this repository (except baseline images).
  - **`External`** — images with a lean public PyPI footprint that are not built from the Red Hat curated index (for example the baseline workbench and runtime ImageStreams in this repository). Use when you need broader PyPI access and accept that you maintain additional packages yourself.
  - **`custom`** — user-built or otherwise non–out-of-the-box images (for example admin-imported ImageStreams). The UI labels these as user-built so they are distinct from shipped Red Hat-provided and External tiers.

- **`opendatahub.io/deprecated:`** - when set to **`"true"`** on the ImageStream `metadata.annotations`, marks the entire workbench image as deprecated (not a single tag). The dashboard shows a **Deprecated** badge next to the tier label, warning helper text when choosing an image (including **Applications > Enabled**), and deprecation status on existing workbenches. Deprecated images remain usable; the goal is to steer users away from ImageStreams that will not receive new version updates. This is separate from per-tag **`opendatahub.io/image-tag-outdated`**: stream-level deprecation means the whole ImageStream is end-of-life, so updating to another tag on the same stream does not restore support—users should select a different workbench image. Omit the annotation or use any value other than `"true"` for images that are still actively maintained.

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
### **Available per-tag annotations**
  - **`opendatahub.io/notebook-software:`** - a string that represents the technology stack included within the workbench image. Each technology in the list is described by its name and the version used (e.g. `'[{"name":"CUDA","version":"11.8"},{"name":"Python","version":"v3.9"}]`')
  - **`opendatahub.io/notebook-python-dependencies:`** -  a string that represents the list of Python libraries included within the workbench image. Each library is described by its name and currently used version (e.g. `'[{"name":"Numpy","version":"1.24"},{"name":"Pandas","version":"1.5"}]'`)
  - **`openshift.io/imported-from:`** - a reference to the image repository where the workbench image was obtained (e.g. `quay.io/repository/opendatahub/workbench-images`)
  - **`opendatahub.io/workbench-image-recommended:`** - a flag that allows the ImageStream tag to be marked as Recommended (used by the UI to distinguish which tags are recommended for use, e.g., when the workbench image offers multiple tags to choose from)
  - **`opendatahub.io/image-tag-outdated:`** - a flag to mark the ImageStream tag as outdated and out of regular maintenance cycle. The image tag will eventually be removed.
  - **`opendatahub.io/notebook-build-commit:`** - a reference to the build commit with the ID to look at the updated information.

### **ImageStream definitions for the supported out-of-the-box images in ODH**

The ImageStream definitions of the out-of-the-box workbench images for ODH can be found in the [notebooks manifests](https://github.com/opendatahub-io/notebooks/tree/main/manifests).

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
    opendatahub.io/recommended-accelerators: '["nvidia.com/gpu", "amd.com/gpu"]'
    opendatahub.io/notebook-tier: "Red Hat-provided"
    opendatahub.io/deprecated: "false"
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
      opendatahub.io/image-tag-outdated: 'false'
    from:
      kind: DockerImage
      name: quay.io/opendatahub/workbench-images@sha256:value-of-the-image-tag
    name: example-tag-name
    referencePolicy:
      type: Source
```
