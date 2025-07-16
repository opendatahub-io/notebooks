from __future__ import annotations

import pathlib
import tempfile

import allure

from tests.containers import conftest, docker_utils
from tests.containers.workbanches.jupyterlab.test_mysql import test_mysql_connection
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer


class TestJupyterLabDatascienceImage:
    """Tests for JupyterLab Workbench images in this repository that are not -minimal-."""

    APP_ROOT_HOME = "/opt/app-root/src"

    def test_mysql_connection(
        self,
        jupyterlab_datascience_image: conftest.Image,
        mysql_container,
        subtests,
    ):
        test_mysql_connection(
            mysql_container, jupyterlab_datascience_image.name, subtests
        )
