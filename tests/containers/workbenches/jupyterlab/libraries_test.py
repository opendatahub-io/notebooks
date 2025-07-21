from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from tests.containers import docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer, grab_and_check_logs

if TYPE_CHECKING:
    import pytest_subtests

    from tests.containers.conftest import Image


class TestWorkbenchImage:
    """Tests for workbench images in this repository.
    A workbench image is an image running a web IDE that listens on port 8888."""

    def test_image_entrypoint_starts(
        self, subtests: pytest_subtests.SubTests, jupyterlab_datascience_image: Image
    ) -> None:
        container = WorkbenchContainer(image=jupyterlab_datascience_image.name, user=1000, group_add=[0])
        try:
            try:
                container.start()
                # check explicitly that we can connect to the ide running in the workbench
                with subtests.test("Attempting to connect to the workbench..."):
                    container._connect()
                unittests = pathlib.Path(__file__).parent / "libraries_testunits.py"
                docker_utils.container_cp(container.get_wrapped_container(), unittests, "/opt/app-root/src/")
                ecode, stdout = container.exec(
                    [
                        "env",
                        f"IMAGE={jupyterlab_datascience_image.labels['name']}",
                        "bash",
                        "-c",
                        "python3 /opt/app-root/src/libraries_testunits.py",
                    ]
                )
                stdout_decoded = stdout.decode()
                print(stdout_decoded)
                assert ecode == 0, stdout_decoded
            finally:
                # try to grab logs regardless of whether container started or not
                grab_and_check_logs(subtests, container)
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)
