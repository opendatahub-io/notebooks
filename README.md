# Notebook Images

These images were created to be used with Open Data Hub (ODH) with the ODH Notebook Controller as the launcher.

## Container Image Layering

The different notebooks images available are built in this order:

```mermaid
graph TB
    subgraph Notebooks
        %% Nodes
        ubi8-python-3.8(UBI8 Python 3.8);
        base-ubi8-python-3.8("Notebooks Base<br/>(base-ubi8-python-3.8)");
        jupyter-minimal-ubi8-python-3.8("Minimal Notebook<br/>(jupyter-minimal-ubi8-python-3.8)");
        jupyter-datascience-ubi8-python-3.8("Data Science Notebook<br/>(jupyter-datascience-ubi8-python-3.8)");

        %% Edges
        ubi8-python-3.8 --> base-ubi8-python-3.8;
        base-ubi8-python-3.8 --> jupyter-minimal-ubi8-python-3.8;
        jupyter-minimal-ubi8-python-3.8 --> jupyter-datascience-ubi8-python-3.8;
    end

    subgraph CUDA
        %% Nodes
        cuda-ubi8-python-3.8("CUDA Notebooks Base<br/>(cuda-ubi8-python-3.8)");
        cuda-jupyter-minimal-ubi8-python-3.8("CUDA Minimal Notebook<br/>(cuda-jupyter-minimal-ubi8-python-3.8)");
        cuda-jupyter-datascience-ubi8-python-3.8("CUDA Data Science Notebook<br/>(cuda-jupyter-datascience-ubi8-python-3.8)");
        cuda-jupyter-pytorch-ubi8-python-3.8("CUDA PyTorch Notebook<br/>(cuda-jupyter-pytorch-ubi8-python-3.8)");
        cuda-jupyter-tensorflow-ubi8-python-3.8("CUDA TensorFlow Notebook<br/>(cuda-jupyter-tensorflow-ubi8-python-3.8)");

        %% Edges
        base-ubi8-python-3.8 --> cuda-ubi8-python-3.8;
        cuda-ubi8-python-3.8 --> cuda-jupyter-minimal-ubi8-python-3.8;
        cuda-jupyter-minimal-ubi8-python-3.8 --> cuda-jupyter-datascience-ubi8-python-3.8;
        cuda-jupyter-datascience-ubi8-python-3.8 --> cuda-jupyter-pytorch-ubi8-python-3.8;
        cuda-jupyter-datascience-ubi8-python-3.8 --> cuda-jupyter-tensorflow-ubi8-python-3.8;
    end
```

## Building

The following notebook images are available:

- jupyter-minimal-ubi8-python-3.8
- jupyter-datascience-ubi8-python-3.8
- cuda-jupyter-minimal-ubi8-python-3.8
- cuda-jupyter-datascience-ubi8-python-3.8
- cuda-jupyter-pytorch-ubi8-python-3.8
- cuda-jupyter-tensorflow-ubi8-python-3.8

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
make ${NOTEBOOK_NAME} -e IMAGE_REGISRY=quay.io/${YOUR_USER}/notebooks
```

## Testing

Deploy the notebook images in your Kubernetes environment:

```shell
make deploy-${NOTEBOOK_NAME}
```

Run the test suite against this notebook:

```shell
make test-${NOTEBOOK_NAME}
```

Clean up the environment when the tests are finished:

```shell
make undeploy-${NOTEBOOK_NAME}
```
