from __future__ import annotations

import pytest

from tests.containers import kubernetes_utils

code = """
import torch; device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"Using {device} device")
"""

# This is from ods-ci,
# https://github.com/red-hat-data-services/ods-ci/blob/ab7237d899c053b0f5b0ff0a2074ac4cdde3543e/ods_ci/tests/Resources/Page/ODH/JupyterHub/GPU.resource#L13-L12
class TestAccelerator:
    @pytest.mark.openshift
    def test_cuda_run_on_openshift(self):
        workbench_image: str = (
            "quay.io/modh/odh-pytorch-notebook@sha256:b5372300cc51478c051edf8431b159641afb84109e4bdd219cd307563b01d53a"
        )
        client = kubernetes_utils.get_client()
        print(client)

        username = kubernetes_utils.get_username(client)
        print(username)

        with kubernetes_utils.ImageDeployment(client, workbench_image) as image:
            image.deploy(container_name="notebook-tests-pod", accelerator="nvidia.com/gpu")
            result = image.exec(f"python -c '{code}'")
            assert "Using cuda device" in result.stdout
