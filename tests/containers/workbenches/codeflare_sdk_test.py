from __future__ import annotations

import allure
import pytest

from tests.containers import base_image_test, conftest, docker_utils


class TestCodeFlareSDK:
    """Smoke tests for the CodeFlare SDK packaged in data science workbenches."""

    @allure.issue("https://github.com/opendatahub-io/notebooks/issues/305")
    @allure.description("Verify that the CodeFlare SDK and its basic configuration API are available.")
    def test_codeflare_sdk_is_available(
        self,
        datascience_image: conftest.Image,
        container_arch: str,
    ) -> None:
        if container_arch in ("ppc64le", "s390x"):
            pytest.skip(f"CodeFlare SDK lock markers exclude the {container_arch} architecture")

        def check_codeflare_sdk() -> None:
            import importlib.metadata  # ruff: ignore[import-outside-top-level]

            import codeflare_sdk  # pyright: ignore[reportMissingImports]  # ruff: ignore[import-outside-top-level]
            from codeflare_sdk import (  # pyright: ignore[reportMissingImports]  # ruff: ignore[import-outside-top-level]
                Cluster,
                ClusterConfiguration,
            )

            version = importlib.metadata.version("codeflare-sdk")
            assert version.startswith("0."), f"Unexpected CodeFlare SDK version: {version}"
            assert codeflare_sdk.__name__ == "codeflare_sdk"
            assert callable(Cluster), "codeflare_sdk.Cluster is not callable"
            assert callable(ClusterConfiguration), "codeflare_sdk.ClusterConfiguration is not callable"
            print(f"CodeFlare SDK smoke test passed: {version}")

        with docker_utils.running_container(datascience_image.name) as container:
            exit_code, output_bytes = container.exec(
                base_image_test.encode_python_function_execution_command_interpreter("python3", check_codeflare_sdk)
            )

        output = output_bytes.decode()
        assert exit_code == 0, f"CodeFlare SDK smoke test failed: {output}"
        assert "CodeFlare SDK smoke test passed:" in output, output
