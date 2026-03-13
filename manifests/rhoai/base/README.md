# IDE Imagestreams

Listing the order in which each imagestreams are introduced based on the `opendatahub.io/notebook-image-order` annotation in each file.

## Notebook Imagestreams (with order annotations):

1. training-hub-universal-cpu-imagestream.yaml (Order: 1) [trainer repo]
2. training-hub-universal-cuda-imagestream.yaml (Order: 2) [trainer repo]
3. training-hub-universal-rocm-imagestream.yaml (Order: 3) [trainer repo]
4. jupyter-minimal-notebook-imagestream.yaml (Order: 4)
5. jupyter-minimal-gpu-notebook-imagestream.yaml (Order: 6)
6. jupyter-rocm-minimal-notebook-imagestream.yaml (Order: 8)
7. jupyter-datascience-notebook-imagestream.yaml (Order: 10)
8. jupyter-pytorch-notebook-imagestream.yaml (Order: 12)
9. jupyter-pytorch-llmcompressor-imagestream.yaml (Order: 13)
10. jupyter-rocm-pytorch-notebook-imagestream.yaml (Order: 15)
11. jupyter-tensorflow-notebook-imagestream.yaml (Order: 17)
12. jupyter-rocm-tensorflow-notebook-imagestream.yaml (Order: 19)
13. jupyter-trustyai-notebook-imagestream.yaml (Order: 19)
14. code-server-notebook-imagestream.yaml (Order: 22)
15. rstudio-gpu-notebook-imagestream.yaml (Order: 25)

## Runtime Imagestreams (no order annotations):

- runtime-datascience-imagestream.yaml
- runtime-minimal-imagestream.yaml
- runtime-pytorch-imagestream.yaml
- runtime-rocm-pytorch-imagestream.yaml
- runtime-rocm-tensorflow-imagestream.yaml
- runtime-tensorflow-imagestream.yaml
- runtime-pytorch-llmcompressor-imagestream.yaml

The order is determined by the `opendatahub.io/notebook-image-order` annotation listed in each imagestream file.  
_Note_: On deprecation/removal of imagestream, the index of that image is retired with it.

## Params file

Please read workbench-naming for the name convention to follow in params.env.  
[Workbench Naming](../../docs/workbenches-naming.md)

- params-latest.env: This file contains references to latest versions of workbench images that are updated by konflux nudges.
- params.env: This file contains references to older versions of workbench images.

Image names follow the established IDE format:
`odh-<image type>-<image-feature>-<image-scope>-<accelerator>-<python-version>-<os-version>`
