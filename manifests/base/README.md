# IDE Imagestreams

Listing the order in which each imagestreams are introduced.
NOTE: In overlays/additional there are new set of Python 3.12 images, they are also included in this ordering

1. jupyter-minimal-notebook-imagestream.yaml
2. jupyter-minimal-cpu-py312-ubi9-imagestream.yaml
3. jupyter-minimal-gpu-notebook-imagestream.yaml
4. jupyter-minimal-cuda-py312-ubi9-imagestream.yaml
5. jupyter-rocm-minimal-notebook-imagestream.yaml
6. jupyter-minimal-rocm-py312-ubi9-imagestream.yaml
7. jupyter-datascience-notebook-imagestream.yaml
8. jupyter-datascience-cpu-py312-ubi9-imagestream.yaml
9. jupyter-pytorch-notebook-imagestream.yaml
10. jupyter-pytorch-cuda-py312-ubi9-imagestream.yaml
11. jupyter-rocm-pytorch-notebook-imagestream.yaml
12. jupyter-pytorch-rocm-py312-ubi9-imagestream.yaml
13. jupyter-tensorflow-notebook-imagestream.yaml
14. jupyter-tensorflow-cuda-py312-ubi9-imagestream.yaml
15. jupyter-rocm-tensorflow-notebook-imagestream.yaml
16. jupyter-trustyai-notebook-imagestream.yaml
17. jupyter-trustyai-cpu-py312-ubi9-imagestream.yaml
18. code-server-notebook-imagestream.yaml
19. codeserver-datascience-cpu-py312-ubi9-imagestream.yaml
20. rstudio-notebook-imagestream.yaml
21. rstudio-gpu-notebook-imagestream.yaml

The order would also be same as `opendatahub.io/notebook-image-order` listed in each imagestreams.  
_Note_: On deprecation/removal of imagestream, the index of that image is retired with it.

## Params file

Please read workbench-naming for the name convention to follow in params.env.  
[Workbench Naming](../../docs/workbenches-naming.md)

- params-latest.env: This file contains references to latest versions of workbench images that are updated by konflux nudges.
- params.env: This file contains references to older versions of workbench images.

Image names follow the established IDE format:
`odh-<image type>-<image-feature>-<image-scope>-<accelerator>-<python-version>-<os-version>`
