# Workbench Naming

The following pattern is designed and would be used for future IDE workbench content:

Workbench Image name schema:

```
odh-<image type>-<image-feature>-<image-scope>-<accelerator>-<python version>-<os-version>
```

- Image prefix: odh
- Image type: workbench, pipeline
- Image feature:
  - jupyter
  - codeserver
  - Rstudio
  - runtime
- Image scope:
  - Minimal
  - DataScience
  - TensorFlow
  - PyTorch
  - Trustyai
- Accelerator: cpu, cuda, rocm
- Python version: 3.11, 3.9, ?3.12
- Image suffix: rhel8, rhel9
  - Community: ubi9, ubi8, c8s , c9s

#### Examples:

Standards example: 

* odh-workbench-jupyter-minimal-cuda-py311-rhel9
* odh-workbench-jupyter-minimal-cpu-py311-rhel9
* odh-workbench-jupyter-minimal-cpu-py312-rhel9
* odh-workbench-codeserver-datascience-cpu-py311-rhel9
* odh-workbench-rstudio-minimal-cuda-py311-rhel9
* odh-pipeline-runtime-minimal-cpu-py311-rhel9



_Motivation_:  
Based on: https://issues.redhat.com/browse/RHOAIENG-21539  
Image Name: Short and meaningful name of the image that will be used for creating build/delivery repositories for the image. The image name must be prefixed with "odh-" and suffixed with the RHEL version (like so: -rhel7, -rhel8).

### Previous Pattern

The workbench image name convention in RHOAI for IDE content was not structured and changed on different image scopes.  
Format: _image_name:tag_  
Example:

- Image:
  - name: odh-pytorch-notebook
  - tag :v3-20250418-c0fa3b2
- Image:
  - name: runtime-images
  - tag: rocm-runtime-tensorflow-ubi9-python-3.11-20250418-c0fa3b2

## Split of params 

Konflux would be help with build of workbenches. Konflux patch the sha of the built image into params file as a process of nudging.  
To keep this file not getting overriden, we have split the params file into 2 files.
- params-latest.env: Any workbench images that represent the nth image.
- params.env: Rest of the workbench images that represent the n-1 and extras.

Note: This same case is followed for commit.env as well.