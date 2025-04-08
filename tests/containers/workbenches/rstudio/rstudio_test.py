from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import tempfile
import textwrap
from typing import TYPE_CHECKING, NamedTuple

import allure
import pytest
import pytest_subtests

from tests.containers import docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    import docker.models.images


class TestRStudioImage:
    """Tests for RStudio Workbench images in this repository."""

    APP_ROOT_HOME = "/opt/app-root/src"

    @allure.issue("RHOAIENG-17256")
    def test_rmd_to_pdf_rendering(self, rstudio_image: docker.models.images.Image) -> None:
        """
        References:
            https://stackoverflow.com/questions/40563479/relationship-between-r-markdown-knitr-pandoc-and-bookdown
            https://www.earthdatascience.org/courses/earth-analytics/document-your-science/knit-rmarkdown-document-to-pdf/
        """
        if "rhel" in rstudio_image.labels["name"]:
            pytest.skip(
                "ISSUE-957, RHOAIENG-17256(comments): RStudio workbench on RHEL does not come with knitr preinstalled"
            )

        container = WorkbenchContainer(image=rstudio_image, user=1000, group_add=[0])
        try:
            container.start(wait_for_readiness=False)

            # language=R
            script = textwrap.dedent("""
                library(knitr)
                library(rmarkdown)
                render("document.Rmd", output_format = "pdf_document")
                """)
            # language=markdown
            document = textwrap.dedent("""
                ---
                title: "Untitled"
                output: pdf_document
                date: "2025-01-22"
                ---

                ```{r setup, include=FALSE}
                knitr::opts_chunk$set(echo = TRUE)
                ```

                ## R Markdown

                This is an R Markdown document. Markdown is a simple formatting syntax for authoring HTML, PDF, and MS Word documents. For more details on using R Markdown see <http://rmarkdown.rstudio.com>.

                When you click the **Knit** button a document will be generated that includes both content as well as the output of any embedded R code chunks within the document. You can embed an R code chunk like this:

                ```{r cars}
                summary(cars)
                ```

                ## Including Plots

                You can also embed plots, for example:

                ```{r pressure, echo=FALSE}
                plot(pressure)
                ```

                Note that the `echo = FALSE` parameter was added to the code chunk to prevent printing of the R code that generated the plot.
                """)

            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = pathlib.Path(tmpdir)
                (tmpdir / "script.R").write_text(script)
                docker_utils.container_cp(
                    container.get_wrapped_container(), src=str(tmpdir / "script.R"), dst=self.APP_ROOT_HOME
                )
                (tmpdir / "document.Rmd").write_text(document)
                docker_utils.container_cp(
                    container.get_wrapped_container(), src=str(tmpdir / "document.Rmd"), dst=self.APP_ROOT_HOME
                )

            # https://stackoverflow.com/questions/28432607/pandoc-version-1-12-3-or-higher-is-required-and-was-not-found-r-shiny
            check_call(
                container,
                f"bash -c 'RSTUDIO_PANDOC=/usr/lib/rstudio-server/bin/quarto/bin/tools/x86_64 Rscript {self.APP_ROOT_HOME}/script.R'",
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                docker_utils.from_container_cp(container.get_wrapped_container(), src=self.APP_ROOT_HOME, dst=tmpdir)
                allure.attach.file(
                    pathlib.Path(tmpdir) / "src/document.pdf",
                    name="rendered-pdf",
                    attachment_type=allure.attachment_type.PDF,
                )

        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

    @allure.issue("RHOAIENG-16604")
    def test_http_proxy_env_propagates(self, rstudio_image: str, subtests: pytest_subtests.plugin.SubTests) -> None:
        """
        This checks that the lowercased proxy configuration is propagated into the RStudio
        environment so that the appropriate values are then accepted and followed.
        """

        class TestCase(NamedTuple):
            name: str
            name_lc: str
            value: str

        test_cases: list[TestCase] = [
            TestCase("HTTP_PROXY", "http_proxy", "http://localhost:8080"),
            TestCase("HTTPS_PROXY", "https_proxy", "https://localhost:8443"),
            TestCase("NO_PROXY", "no_proxy", "google.com"),
        ]

        container = WorkbenchContainer(image=rstudio_image, user=1000, group_add=[0])
        for tc in test_cases:
            container.with_env(tc.name, tc.value)

        try:
            # We need to wait for the IDE to be completely loaded so that the envs are processed properly.
            container.start(wait_for_readiness=True)

            # Once the RStudio IDE is fully up and running, the processed envs should includ also lowercased proxy configs.
            for tc in test_cases:
                with subtests.test(tc.name):
                    output = check_output(container, f"/usr/bin/R --quiet --no-echo -e 'Sys.getenv(\"{tc.name_lc}\")'")
                    assert '"' + tc.value + '"' in output
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)


def check_call(container: WorkbenchContainer, cmd: str) -> int:
    """Like subprocess.check_output, but in a container."""
    logging.debug(_("Running command", cmd=cmd))
    rc, result = container.exec(cmd)
    result = result.decode("utf-8")
    logging.debug(_("Command execution finished", rc=rc, result=result))
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd, output=result)
    return rc


def check_output(container: WorkbenchContainer, cmd: str) -> str:
    """Like subprocess.check_output, but in a container."""
    logging.debug(_("Running command", cmd=cmd))
    rc, result = container.exec(cmd)
    result = result.decode("utf-8")
    logging.debug(_("Command execution finished", rc=rc, result=result))
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd, output=result)
    return result


class StructuredMessage:
    """https://docs.python.org/3/howto/logging-cookbook.html#implementing-structured-logging"""

    def __init__(self, message, /, **kwargs):
        self.message = message
        self.kwargs = kwargs

    def __str__(self):
        s = Encoder().encode(self.kwargs)
        return "%s >>> %s" % (self.message, s)


class Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, set):
            return tuple(o)
        elif isinstance(o, str):
            return o.encode("unicode_escape").decode("ascii")
        return super().default(o)


_ = StructuredMessage  # optional shortcut, to improve readability
