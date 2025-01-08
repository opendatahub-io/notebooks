imagestream = """
---
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  labels:
    opendatahub.io/notebook-image: "true"
  annotations:
    opendatahub.io/notebook-image-url: "https://github.com//opendatahub-io/notebooks/tree/main/jupyter/minimal"
    opendatahub.io/notebook-image-name: "Minimal Python"
    opendatahub.io/notebook-image-desc: "Jupyter notebook image with minimal dependency set to start experimenting with Jupyter environment."
    opendatahub.io/notebook-image-order: "1"
  name: jupyter-minimal-notebook
spec:
  lookupPolicy:
    local: true
  tags:
    # N Version of the image
    - annotations:
        # language=json
        opendatahub.io/notebook-software: |
          [
            {"name": "Python", "version": "v3.11"}
          ]
        # language=json
        opendatahub.io/notebook-python-dependencies: |
          [
            {"name": "JupyterLab","version": "4.2"}
          ]
        openshift.io/imported-from: quay.io/opendatahub/workbench-images
        opendatahub.io/workbench-image-recommended: 'true'
        opendatahub.io/default-image: "true"
        opendatahub.io/notebook-build-commit: $(odh-minimal-notebook-image-commit-n)
      from:
        kind: DockerImage
        name: $(odh-minimal-notebook-image-n)
      name: "2024.2"
      referencePolicy:
        type: Source
    # N Version of the image
    - annotations:
        # language=json
        opendatahub.io/notebook-software: |
          [
            {"name": "Python", "version": "v3.9"}
          ]
        # language=json
        opendatahub.io/notebook-python-dependencies: |
          [
            {"name": "JupyterLab","version": "3.6"},
            {"name": "Notebook","version": "6.5"}
          ]
        openshift.io/imported-from: quay.io/opendatahub/workbench-images
        opendatahub.io/workbench-image-recommended: 'false'
        opendatahub.io/default-image: "true"
        opendatahub.io/notebook-build-commit: $(odh-minimal-notebook-image-commit-n-1)
      from:
        kind: DockerImage
        name: $(odh-minimal-notebook-image-n-1)
      name: "2024.1"
      referencePolicy:
        type: Source
"""
