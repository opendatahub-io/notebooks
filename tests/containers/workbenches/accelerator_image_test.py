from __future__ import annotations

import shlex

import pytest

from tests.containers import conftest, kubernetes_utils

code = """
import torch; device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"Using {device} device")
"""


# This is from ods-ci,
# https://github.com/red-hat-data-services/ods-ci/blob/ab7237d899c053b0f5b0ff0a2074ac4cdde3543e/ods_ci/tests/Resources/Page/ODH/JupyterHub/GPU.resource#L13-L12
class TestAccelerator:
    @pytest.mark.cuda
    @pytest.mark.openshift
    # image must be both jupyterlab image and cuda workbench image
    def test_cuda_run_on_openshift(self, jupyterlab_image, cuda_workbench_image):
        client = kubernetes_utils.get_client()
        print(client)

        image_metadata = conftest.get_image_metadata(cuda_workbench_image)
        library = None
        if "-pytorch-" in image_metadata.labels.get("name"):
            library = "torch"
        if "-tensorflow-" in image_metadata.labels.get("name"):
            library = "tensorflow"

        # language=python
        torch_check = (
            """import torch; device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"Using {device} device")"""
        )
        # language=python
        tensorflow_check = """import tensorflow as tf; import os; os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'; print(tf.config.list_physical_devices('GPU'))"""

        with kubernetes_utils.ImageDeployment(client, cuda_workbench_image) as image:
            image.deploy(container_name="notebook-tests-pod", accelerator="nvidia.com/gpu")
            if library == "torch":
                result = image.exec(shlex.join(["python", "-c", torch_check]))
                assert "Using cuda device" in result.stdout
            elif library == "tensorflow":
                result = image.exec(shlex.join(["python", "-c", tensorflow_check]))
                assert "[PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]" in result.stdout
            else:
                raise ValueError(f"Unknown library {library}")
