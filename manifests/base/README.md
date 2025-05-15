# IDE Imagestreams

Listing the order in which each imagestreams are introduced.

1. jupyter-minimal-notebook-imagestream.yaml
2. jupyter-datascience-notebook-imagestream.yaml
3. jupyter-minimal-gpu-notebook-imagestream.yaml
4. jupyter-pytorch-notebook-imagestream.yaml
5. jupyter-tensorflow-notebook-imagestream.yaml
6. jupyter-trustyai-notebook-imagestream.yaml
8. code-server-notebook-imagestream.yaml
9. rstudio-notebook-imagestream.yaml
10. rstudio-gpu-notebook-imagestream.yaml
11. jupyter-rocm-minimal-notebook-imagestream.yaml
12. jupyter-rocm-pytorch-notebook-imagestream.yaml
13. jupyter-rocm-tensorflow-notebook-imagestream.yaml

The order would also be same as `opendatahub.io/notebook-image-order` listed in each imagestreams.  
_Note_: On deprecation/removal of imagestream, the index of that image is retired with it.

## Params file

Please read workbench-naming for the name convention to follow in params.env.  
[Workbench Naming](../../docs/workbenches-naming.md)

- params-latest.env: This file contains references to latest versions of workbench images that are updated by konflux nudges.
- params.env: This file contains references to older versions of workbench images.

Image names follow the established IDE format:
`odh-<image type>-<image-feature>-<image-scope>-<accelerator>-<python-version>-<os-version>`
