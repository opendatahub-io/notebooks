from __future__ import annotations

from typing import TYPE_CHECKING

import allure
import requests

from tests.containers import docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    import docker.models.images


class TestJupyterLabImage:
    """Tests for JupyterLab Workbench images in this repository."""

    APP_ROOT_HOME = "/opt/app-root/src"

    @allure.issue("RHOAIENG-11156")
    @allure.description("Check that the HTML for the spinner is contained in the initial page.")
    def test_spinner_html_loaded(self, jupyterlab_image: docker.models.images.Image) -> None:
        container = WorkbenchContainer(image=jupyterlab_image, user=4321, group_add=[0])
        # if no env is specified, the image will run
        # > 4321        3334    3319  0 10:36 pts/0    00:00:01 /mnt/rosetta /opt/app-root/bin/python3.11 /opt/app-root/bin/jupyter-lab
        # > --ServerApp.root_dir=/opt/app-root/src --ServerApp.ip= --ServerApp.allow_origin=* --ServerApp.open_browser=False
        # which does not let us open a notebook and get a spinner, we need to disable auth at a minimum

        # These NOTEBOOK_ARGS are what ODH Dashboard uses,
        # and we also have them in the Kustomize test files for Makefile tests
        container.with_env(
            "NOTEBOOK_ARGS",
            "\n".join(  # noqa: FLY002 Consider f-string instead of string join
                [
                    "--ServerApp.port=8888",
                    "--ServerApp.token=''",
                    "--ServerApp.password=''",
                    "--ServerApp.base_url=/notebook/opendatahub/jovyan",
                    "--ServerApp.quit_button=False",
                    """--ServerApp.tornado_settings={"user":"jovyan","hub_host":"https://opendatahub.io","hub_prefix":"/notebookController/jovyan"}""",
                ]
            ),
        )
        try:
            # we changed base_url, and wait_for_readiness=True would attempt connections to /
            container.start(wait_for_readiness=False)
            container._connect(base_url="/notebook/opendatahub/jovyan")

            host_ip = container.get_container_host_ip()
            host_port = container.get_exposed_port(container.port)
            response = requests.get(f"http://{host_ip}:{host_port}/notebook/opendatahub/jovyan")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert 'class="pf-v6-c-spinner"' in response.text
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)
