from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import tempfile
import textwrap
from typing import TYPE_CHECKING

import allure
import pytest

from tests.containers import docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer, skip_if_not_workbench_image

if TYPE_CHECKING:
    import docker.models.images


class TestRStudioImage:
    """Tests for RStudio Workbench images in this repository."""

    @allure.issue("RHOAIENG-17256")
    def test_rmd_to_pdf_rendering(self, image: str) -> None:
        """
        References:
            https://stackoverflow.com/questions/40563479/relationship-between-r-markdown-knitr-pandoc-and-bookdown
            https://www.earthdatascience.org/courses/earth-analytics/document-your-science/knit-rmarkdown-document-to-pdf/
        """
        skip_if_not_rstudio_image(image)

        container = WorkbenchContainer(image=image, user=1000, group_add=[0])
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
                docker_utils.container_cp(container.get_wrapped_container(), src=str(tmpdir / "script.R"),
                                          dst="/scripts")
                (tmpdir / "document.Rmd").write_text(document)
                docker_utils.container_cp(container.get_wrapped_container(), src=str(tmpdir / "document.Rmd"),
                                          dst="/scripts")

            # copy to a (writable) working directory
            check_call(container, "bash -c 'cp /scripts/document.Rmd ./'")
            # https://stackoverflow.com/questions/28432607/pandoc-version-1-12-3-or-higher-is-required-and-was-not-found-r-shiny
            check_call(container,
                         "bash -c 'RSTUDIO_PANDOC=/usr/lib/rstudio-server/bin/quarto/bin/tools/x86_64 Rscript /scripts/script.R'")

            with tempfile.TemporaryDirectory() as tmpdir:
                docker_utils.from_container_cp(container.get_wrapped_container(), src="/opt/app-root/src/", dst=tmpdir)
                allure.attach.file(
                    pathlib.Path(tmpdir) / "src/document.pdf",
                    name="rendered-pdf",
                    attachment_type=allure.attachment_type.PDF
                )

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


def skip_if_not_rstudio_image(image: str) -> docker.models.images.Image:
    image_metadata = skip_if_not_workbench_image(image)
    if "-rstudio-" not in image_metadata.labels['name']:
        pytest.skip(
            f"Image {image} does not have '-rstudio-' in {image_metadata.labels['name']=}'")

    return image_metadata


class StructuredMessage:
    """https://docs.python.org/3/howto/logging-cookbook.html#implementing-structured-logging"""

    def __init__(self, message, /, **kwargs):
        self.message = message
        self.kwargs = kwargs

    def __str__(self):
        s = Encoder().encode(self.kwargs)
        return '%s >>> %s' % (self.message, s)


class Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, set):
            return tuple(o)
        elif isinstance(o, str):
            return o.encode('unicode_escape').decode('ascii')
        return super().default(o)


_ = StructuredMessage  # optional shortcut, to improve readability
