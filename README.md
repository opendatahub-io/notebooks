# Notebook Images

These images were created to be used with Open Data Hub (ODH) with the ODH Notebook Controller as the launcher.

## Container Image Layering

The different notebooks images available are built in this order:

**Based on Python 3.8**

```mermaid
graph TB
    subgraph Notebooks
        %% Nodes
        ubi8-python-3.8(UBI8 Python 3.8);
        base-ubi8-python-3.8("Notebooks Base<br/>(base-ubi8-python-3.8)");
        jupyter-minimal-ubi8-python-3.8("Minimal Notebook<br/>(jupyter-minimal-ubi8-python-3.8)");
        jupyter-datascience-ubi8-python-3.8("Data Science Notebook<br/>(jupyter-datascience-ubi8-python-3.8)");
        jupyter-pytorch-ubi8-python-3.8("PyTorch Notebook<br/>(jupyter-pytorch-ubi8-python-3.8)");

        %% Edges
        ubi8-python-3.8 --> base-ubi8-python-3.8;
        base-ubi8-python-3.8 --> jupyter-minimal-ubi8-python-3.8;
        jupyter-minimal-ubi8-python-3.8 --> jupyter-datascience-ubi8-python-3.8;
        jupyter-datascience-ubi8-python-3.8 --> jupyter-pytorch-ubi8-python-3.8;
    end

    subgraph CUDA
        %% Nodes
        cuda-ubi8-python-3.8("CUDA Notebooks Base<br/>(cuda-ubi8-python-3.8)");
        cuda-jupyter-minimal-ubi8-python-3.8("CUDA Minimal Notebook<br/>(cuda-jupyter-minimal-ubi8-python-3.8)");
        cuda-jupyter-datascience-ubi8-python-3.8("CUDA Data Science Notebook<br/>(cuda-jupyter-datascience-ubi8-python-3.8)");
        cuda-jupyter-tensorflow-ubi8-python-3.8("CUDA TensorFlow Notebook<br/>(cuda-jupyter-tensorflow-ubi8-python-3.8)");

        %% Edges
        base-ubi8-python-3.8 --> cuda-ubi8-python-3.8;
        cuda-ubi8-python-3.8 --> cuda-jupyter-minimal-ubi8-python-3.8;
        cuda-jupyter-minimal-ubi8-python-3.8 --> cuda-jupyter-datascience-ubi8-python-3.8;
        cuda-jupyter-datascience-ubi8-python-3.8 --> cuda-jupyter-tensorflow-ubi8-python-3.8;
    end
```

**Based on Python 3.9**

```mermaid
graph TB
    subgraph Notebooks
        %% Nodes
        ubi9-python-3.9(UBI9 Python 3.9);
        base-ubi9-python-3.9("Notebooks Base<br/>(base-ubi9-python-3.9)");
        jupyter-minimal-ubi9-python-3.9("Minimal Notebook<br/>(jupyter-minimal-ubi9-python-3.9)");
        jupyter-datascience-ubi9-python-3.9("Data Science Notebook<br/>(jupyter-datascience-ubi9-python-3.9)");
        jupyter-pytorch-ubi9-python-3.9("PyTorch Notebook<br/>(jupyter-pytorch-ubi9-python-3.9)");

        %% Edges
        ubi9-python-3.9 --> base-ubi9-python-3.9;
        base-ubi9-python-3.9 --> jupyter-minimal-ubi9-python-3.9;
        jupyter-minimal-ubi9-python-3.9 --> jupyter-datascience-ubi9-python-3.9;
        jupyter-datascience-ubi9-python-3.9 --> jupyter-pytorch-ubi9-python-3.9;
    end

    subgraph CUDA
        %% Nodes
        cuda-ubi9-python-3.9("CUDA Notebooks Base<br/>(cuda-ubi9-python-3.9)");
        cuda-jupyter-minimal-ubi9-python-3.9("CUDA Minimal Notebook<br/>(cuda-jupyter-minimal-ubi9-python-3.9)");
        cuda-jupyter-datascience-ubi9-python-3.9("CUDA Data Science Notebook<br/>(cuda-jupyter-datascience-ubi9-python-3.9)");
        cuda-jupyter-tensorflow-ubi9-python-3.9("CUDA TensorFlow Notebook<br/>(cuda-jupyter-tensorflow-ubi9-python-3.9)");

        %% Edges
        base-ubi9-python-3.9 --> cuda-ubi9-python-3.9;
        cuda-ubi9-python-3.9 --> cuda-jupyter-minimal-ubi9-python-3.9;
        cuda-jupyter-minimal-ubi9-python-3.9 --> cuda-jupyter-datascience-ubi9-python-3.9;
        cuda-jupyter-datascience-ubi9-python-3.9 --> cuda-jupyter-tensorflow-ubi9-python-3.9;
    end

```

## Building

The following notebook images are available:

### Python 3.8
- jupyter-minimal-ubi8-python-3.8
- jupyter-datascience-ubi8-python-3.8
- jupyter-pytorch-ubi8-python-3.8
- cuda-jupyter-minimal-ubi8-python-3.8
- cuda-jupyter-datascience-ubi8-python-3.8
- cuda-jupyter-tensorflow-ubi8-python-3.8

### Python 3.9
- jupyter-minimal-ubi9-python-3.9
- jupyter-datascience-ubi9-python-3.9
- jupyter-pytorch-ubi9-python-3.9
- cuda-jupyter-minimal-ubi9-python-3.9
- cuda-jupyter-datascience-ubi9-python-3.9
- cuda-jupyter-tensorflow-ubi9-python-3.9

If you want to manually build a notebook image, you can use the following
command:

```shell
make ${NOTEBOOK_NAME}
```

The image will be built and pushed to the
[quay.io/opendatahub/notebooks](https://quay.io/opendatahub/notebooks)
repository.

You can use a different registry by overwriting the `IMAGE_REGISTRY` variable:

```shell
make ${NOTEBOOK_NAME} -e IMAGE_REGISTRY=quay.io/${YOUR_USER}/notebooks
```

## Testing

Deploy the notebook images in your Kubernetes environment using deploy8-${NOTEBOOK_NAME} for ubi8 or deploy9-${NOTEBOOK_NAME} for ubi9:

```shell
make deployX-${NOTEBOOK_NAME}
```

Run the test suite against this notebook:

```shell
make test-${NOTEBOOK_NAME}
```

Clean up the environment when the tests are finished:

```shell
make undeployX-${NOTEBOOK_NAME}
```

For further information please see [CONTRIBUTING.md](CONTRIBUTING.md) file.
