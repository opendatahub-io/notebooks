# Conda Notebook Images

This Notebooks image are managed with [Anaconda](https://anaconda.org/).

## Manage the conda environment

```
cd base/anaconda-python-3.8
podman build -t conda-base . 

cd jupyter/datascience/anaconda-python-3.8
podman run -it localhost/conda-base bash

(on a different terminal) podman cp environment.yml <container_id>/environment.yml

conda env update -n workbench --file environment.yml --prune
conda env export > environment.yml

(on a different terminal) podman cp <container_id>/environment.yml .
```


Reference docs: https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#activating-an-environment 

