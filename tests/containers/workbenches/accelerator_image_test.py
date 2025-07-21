from __future__ import annotations

import shlex

import pytest

from tests.containers import conftest, kubernetes_utils
from tests.containers.kubernetes_utils import TestFrameConstants

code = """
import torch; device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"Using {device} device")
"""


# This is from ods-ci,
# https://github.com/red-hat-data-services/ods-ci/blob/ab7237d899c053b0f5b0ff0a2074ac4cdde3543e/ods_ci/tests/Resources/Page/ODH/JupyterHub/GPU.resource#L13-L12
class TestAccelerator:
    @pytest.mark.cuda
    @pytest.mark.openshift
    # image must be both a datascience image and cuda image
    def test_cuda_run_on_openshift(self, datascience_image, cuda_image):
        client = kubernetes_utils.get_client()
        print(client)

        image_metadata = conftest.get_image_metadata(cuda_image)
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

        with kubernetes_utils.ImageDeployment(client, cuda_image) as image:
            image.deploy(
                container_name="notebook-tests-pod",
                accelerator="nvidia.com/gpu",
                is_runtime_image="-runtime-" in image_metadata.labels.get("name"),
                timeout=TestFrameConstants.TIMEOUT_20MIN,
            )
            if library == "torch":
                result = image.exec(shlex.join(["python", "-c", torch_check]))
                assert "Using cuda device" in result.stdout
            elif library == "tensorflow":
                result = image.exec(shlex.join(["python", "-c", tensorflow_check]))
                assert "[PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]" in result.stdout
            else:
                raise ValueError(f"Unknown library {library}")

    @pytest.mark.rocm
    @pytest.mark.openshift
    # image must be both a datascience image and rocm image
    def test_rocm_run_on_openshift(self, datascience_image, rocm_image):
        client = kubernetes_utils.get_client()
        print(client)

        image_metadata = conftest.get_image_metadata(rocm_image)
        library = None
        if "-pytorch-" in image_metadata.labels.get("name"):
            library = "torch"
        if "-tensorflow-" in image_metadata.labels.get("name"):
            library = "tensorflow"

        # NOTE: the basic check is exactly the same as for cuda; in torch, even though it says "cuda", it is actually ROCm

        # language=python
        torch_check = (
            """import torch; device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"Using {device} device")"""
        )
        # language=python
        tensorflow_check = """import tensorflow as tf; import os; os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'; print(tf.config.list_physical_devices('GPU'))"""

        with kubernetes_utils.ImageDeployment(client, rocm_image) as image:
            image.deploy(
                container_name="notebook-tests-pod",
                accelerator="amd.com/gpu",
                is_runtime_image="-runtime-" in image_metadata.labels.get("name"),
                timeout=TestFrameConstants.TIMEOUT_20MIN,
            )
            if library == "torch":
                result = image.exec(shlex.join(["python", "-c", torch_check]))
                assert "Using cuda device" in result.stdout
            elif library == "tensorflow":
                result = image.exec(shlex.join(["python", "-c", tensorflow_check]))
                assert "[PhysicalDevice(name='/physical_device:GPU:0', device_type='GPU')]" in result.stdout
            else:
                raise ValueError(f"Unknown library {library}")
