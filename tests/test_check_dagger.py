from __future__ import annotations

import pathlib
import sys
import logging

import dagger

from tests import ROOT_PATH

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pyfakefs.fake_filesystem import FakeFilesystem

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT = 10 * 60

async def test_something_with_papermill():
    async with (dagger.Connection(dagger.Config(log_output=sys.stderr)) as client):
        # build = client.host().directory(".").docker_build()
        # await build.publish("jeremyatdockerhub/myexample:latest")
        notebook_name = "minimal"
        ubi_flavor = "ubi9"
        python_kernel = "python-3.9"
        image = "ghcr.io/jiridanek/notebooks/workbench-images:jupyter-minimal-ubi9-python-3.9-jd_helpful_error_751147cd93fed327e940670edbc99c6f44a1ac24"
        r = client.host().directory(str(ROOT_PATH / "jupyter" / notebook_name / f"{ubi_flavor}-{python_kernel}" / "test"))
        c = (client.container()
             .from_(image)
             .with_directory("/test", r)
             )

        d = (c
             .with_exec(["/bin/sh", "-c", "python3 -m pip install papermill"])
             .with_workdir("/opt/app-data").with_exec(["python3", "-m", "papermill", "/test/test_notebook.ipynb", "output.ipynb", "--kernel", "python3", "--stderr-file", "error.txt"]))
        out = await d.stdout()
        print("baf", out)

# https://archive.docs.dagger.io/0.9/421437/work-with-host-filesystem/#important-notes


# def run_kubectl(args: list[str], check=True, background=False, stdout=None, stderr=None) -> subprocess.Popen | subprocess.CompletedProcess:
#     return run_command([str(ROOT_PATH / 'bin/kubectl')] + args, check=check, background=background, stdout=stdout, stderr=stderr)
#
#
# def run_command(args: list[str], check=True, background=False, stdout=None, stderr=None):
#     p = subprocess.Popen(args, text=True, stdout=stdout, stderr=stderr)
#     LOGGER.info(f"Running command: {shlex.join(args)}")
#     if background:
#         return p
#     stdout, stderr = p.communicate(timeout=COMMAND_TIMEOUT)
#     if stdout:
#         LOGGER.debug(f"Command output: {stdout}")
#     if check and p.returncode != 0:
#         raise subprocess.CalledProcessError(p.returncode, shlex.join(args), stdout, stderr)
#     return subprocess.CompletedProcess(args, p.returncode, stdout, stderr)


# class Substring(str):
#     # """
#     # >>> match Substring("abrakadabra"):
#     # ...    case "raka":  # matches
#     # ...        pass
#     # """
#     __eq__ = str.__contains__

# def test_jupyter_minimal_ubi9_python_3_9():
#     test_notebook(notebook_name="jupyter-minimal-ubi9-python-3.9")
#
# def test_jupyter_datascience_ubi9_python_3_9():
#     test_notebook(notebook_name="jupyter-datascience-ubi9-python-3.9")
#
# def test_notebook(notebook_name) -> None:
#     notebook_name = notebook_name.replace("cuda-", "").replace(".", "-")
#     LOGGER.info("# Running tests for $(NOTEBOOK_NAME) notebook...")
#     # Verify the notebook's readiness by pinging the /api endpoint
#     run_kubectl(["wait", "--for=condition=ready", "pod", "-l", f"app={notebook_name}", "--timeout=600s"])
#     with run_kubectl(["port-forward", f"svc/{notebook_name}-notebook", "8888:8888"], background=True) as p:
#         run_command(["curl", "--retry", "25", "--retry-delay", "1", "--retry-connrefused",
#                      "http://localhost:8888/notebook/opendatahub/jovyan/api"])
#         p.kill()
#     full_notebook_name = run_kubectl(["get", "pods", "-l", f"app={notebook_name}", "-o", "custom-columns=:metadata.name"], stdout=subprocess.PIPE).stdout.strip()
#
#     match Substring(full_notebook_name):
#         case "minimal-ubi9":
#             test_with_papermill(full_notebook_name, "minimal", "ubi9", "python-3.9")
#         case "datascience-ubi9":
#             validate_ubi9_datascience(full_notebook_name)
#         case "pytorch-ubi9":
#             validate_ubi9_datascience(full_notebook_name)
#             test_with_papermill("pytorch", "ubi9", "python-3.9")
#         case "tensorflow-ubi9":
#             validate_ubi9_datascience(full_notebook_name)
#             test_with_papermill("tensorflow", "ubi9", "python-3.9")
#         case "trustyai-ubi9":
#             validate_ubi9_datascience(full_notebook_name)
#             test_with_papermill("trustyai", "ubi9", "python-3.9")
#         case "minimal-ubi8":
#             test_with_papermill("minimal", "ubi8", "python-3.8")
#         case "datascience-ubi8":
#             validate_ubi8_datascience(full_notebook_name)
#         case "trustyai-ubi8":
#             validate_ubi8_datascience(full_notebook_name)
#             test_with_papermill("trustyai", "ubi8", "python-3.8")
#         case "anaconda":
#             print("There is no test notebook implemented yet for Anaconda Notebook....")
#         case _:
#             print(f"No matching condition found for {full_notebook_name}.")


# def test_with_tenacity() -> None:

# NOTEBOOK_REPO_BRANCH_BASE = os.environ.get("NOTEBOOK_REPO_BRANCH_BASE") or "https://raw.githubusercontent.com/opendatahub-io/notebooks/main"
# NOTEBOOK_REPO_BRANCH_BASE = os.environ.get("NOTEBOOK_REPO_BRANCH_BASE") or "https://raw.githubusercontent.com/jiridanek/notebooks/jd_update_nbformat"
#
#

REQUIRED_RUNTIME_IMAGE_COMMANDS=["curl", "python3"]
REQUIRED_CODE_SERVER_IMAGE_COMMANDS=["curl", "python", "oc", "code-server"]
REQUIRED_R_STUDIO_IMAGE_COMMANDS=["curl", "python", "oc", "/usr/lib/rstudio-server/bin/rserver"]

#     # Function for testing a notebook with papermill
# #   ARG 1: Notebook name
# #   ARG 1: UBI flavor
# #   ARG 1: Python kernel
# def test_with_papermill(full_notebook_name, notebook_name, ubi_flavor, python_kernel):
#     run_kubectl(['exec', full_notebook_name, '--', '/bin/sh', "-c", "python3 -m pip install papermill"])
#     r = run_kubectl(['exec', full_notebook_name, '--', '/bin/sh', "-c",
#                      f"wget {NOTEBOOK_REPO_BRANCH_BASE}/jupyter/{notebook_name}/{ubi_flavor}-{python_kernel}/test/test_notebook.ipynb -O test_notebook.ipynb"
#                      f" && python3 -m papermill test_notebook.ipynb {notebook_name}_{ubi_flavor}_output.ipynb --kernel python3 --stderr-file {notebook_name}_{ubi_flavor}_error.txt"], check=False)
#     if r.returncode != 0:
#         LOGGER.error(f"ERROR: The {notebook_name} {ubi_flavor} notebook encountered a failure."
#                      f" To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-$(1)-$(2)-$(3)-test-e2e' directory or run 'cat $(1)_$(2)_error.txt' within your container."
#                      f" The make process has been aborted.")
#         assert False
#     else:
#         r = run_kubectl(["exec", full_notebook_name, "--", "/bin/sh", "-c", f"cat {notebook_name}_{ubi_flavor}_error.txt | grep --quiet FAILED"], check=False)
#         if r.returncode == 0:
#             LOGGER.error(f"ERROR: The {notebook_name} {ubi_flavor} notebook encountered a failure. The make process has been aborted.")
#             run_kubectl(["exec", full_notebook_name, "--", "/bin/sh", "-c", f"cat {notebook_name}_{ubi_flavor}_error.txt"])
#             assert False


# def validate_ubi9_datascience(full_notebook_name):
#     test_with_papermill(full_notebook_name, "minimal", "ubi9", "python-3.9")
#     test_with_papermill(full_notebook_name, "datascience", "ubi9", "python-3.9")
#
# def validate_ubi8_datascience(full_notebook_name):
#     test_with_papermill(full_notebook_name,"minimal","ubi8","python-3.8")
#     test_with_papermill(full_notebook_name,"datascience","ubi8","python-3.8")

async def test_validate_runtime_image():
    LOGGER.info("# Running tests for $(NOTEBOOK_NAME) runtime...")
    # run_kubectl(["wait", "--for=condition=ready", "pod", "runtime-pod", "--timeout=300s"])
    # LOGGER.error("Usage: make validate-runtime-image image=<container-image-name>")
    # fail = False
    image = "ghcr.io/jiridanek/notebooks/workbench-images:runtime-minimal-ubi9-python-3.9-jd_helpful_error_751147cd93fed327e940670edbc99c6f44a1ac24"
    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        c = (client.container().from_(image))
        for cmd in REQUIRED_RUNTIME_IMAGE_COMMANDS:
            LOGGER.info("=> Checking container image $$image for $$cmd...")
            # r = run_kubectl(["exec", f"runtime-pod", "which {cmd} > /dev/null 2>&1"], check=False)
            await c.with_exec(["/bin/bash", "-c", f"which {cmd} > /dev/null 2>&1"])
        # if r.returncode != 0:
        #     LOGGER.error("ERROR: Container image $$image  does not meet criteria for command: $$cmd")
        #     fail = True
        #     continue
        # if cmd == "python3":

        LOGGER.info("=> Checking notebook execution...")
        # await c.with_exec(use_entrypoint=True, args=[])
        # print("default artgs", await c.default_args())
        # TODO: I don't see elyra/ directory on the image
        # await c.with_exec(["/bin/bash", "-c", "python3 -m pip install -r /opt/app-root/elyra/requirements-elyra.txt"
        #                                       " && curl https://raw.githubusercontent.com/nteract/papermill/main/papermill/tests/notebooks/simple_execute.ipynb --output simple_execute.ipynb"
        #                                       " && python3 -m papermill simple_execute.ipynb output.ipynb > /dev/null"])
            # r = run_kubectl(["exec", "runtime-pod", "/bin/sh", "-c", , check=False)
            # if r.returncode != 0:
            #     LOGGER.error("ERROR: Image does not meet Python requirements criteria in requirements-elyra.txt")
            #     fail = True
    # assert not fail, "=> ERROR: Container image $$image is not a suitable Elyra runtime image"
    # LOGGER.info(f"=> Container image {image} is a suitable Elyra runtime image")

async def test_validate_codeserver_image():
    # codeserver_pod_ready = run_kubectl(
    #     ["wait", "--for=condition=ready", "pod", "codeserver-pod", "--timeout=300s"], check=False)
    # assert codeserver_pod_ready.returncode == 0, "Code-server pod did not become ready within expected time"

    # assert image, "Usage: make validate-codeserver-image image=<container-image-name>"

    image = "ghcr.io/jiridanek/notebooks/workbench-images:codeserver-ubi9-python-3.9-jd_helpful_error_751147cd93fed327e940670edbc99c6f44a1ac24"
    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        c = (client.container().from_(image))
        for cmd in REQUIRED_CODE_SERVER_IMAGE_COMMANDS:
            await c.with_exec(["/bin/bash", "-c", f"which {cmd} > /dev/null 2>&1"])
            # result = run_kubectl(["exec", "codeserver-pod", f"which {cmd} > /dev/null 2>&1"], check=False)
            # assert result.returncode == 0, f"ERROR: Container image {image} does not meet criteria for command: {cmd}"

# async def validate_rstudio_image(client: dagger.Client, c: dagger.Container):
async def test_validate_rstudio_image():
    image = "ghcr.io/jiridanek/notebooks/workbench-images:rstudio-c9s-python-3.9-jd_helpful_error_751147cd93fed327e940670edbc99c6f44a1ac24"

    notebook_name = ""
    ubi_flavor = "c9s"
    python_kernel = "python-3.9"

    async with (dagger.Connection(dagger.Config(log_output=sys.stderr)) as client):
        c = (client.container()
         .from_(image))

        # $(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
        LOGGER.info("# Running tests for $(NOTEBOOK_NAME) RStudio Server image...")
        # rstudo_pod_ready = run_kubectl(["wait", "--for=condition=ready", "pod", "rstudio-pod", "--timeout=300s"], check=False)
        # assert rstudo_pod_ready.returncode == 0, "Code-server pod did not become ready within expected time"
        # assert image, "Usage: make validate-rstudio-image image=<container-image-name>"

        LOGGER.info("=> Checking container image $$image for package intallation...")
        c = c.with_exec(["/bin/bash", "-c", "mkdir -p /opt/app-root/src/R/temp-library > /dev/null 2>&1"])
        c = c.with_exec(["/bin/bash", "-c", '''R -e "install.packages('tinytex', lib='/opt/app-root/src/R/temp-library')" > /dev/null 2>&1'''])
        await c

        for cmd in REQUIRED_R_STUDIO_IMAGE_COMMANDS:
            LOGGER.info(f"=> Checking container image {image} for {cmd}...")
            # which_cmd = run_kubectl(["exec", "rstudio-pod", f"which {cmd} > /dev/null 2>&1"], check=False)
            await c.with_exec(["/bin/bash", "-c", f"which {cmd} > /dev/null 2>&1"])
            # if which_cmd.returncode == 0:
            #     LOGGER.info(f"{cmd} executed successfully!")
            # else:
            #     LOGGER.error("ERROR: Container image {image}  does not meet criteria for command: {cmd}")
            #     fail = True
            #     continue

        LOGGER.info("=> Fetching R script from URL and executing on the container...")
        # run_command(["curl", "-sSL", "-o", "test_script.R" f"{NOTEBOOK_REPO_BRANCH_BASE}/rstudio/c9s-python-3.9/test/test_script.R"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # run_kubectl(["cp", "test_script.R", "rstudio-pod:/opt/app-root/src/test_script.R"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # test_script = run_kubectl(["exec", "rstudio-pod", "--", "Rscript /opt/app-root/src/test_script.R > /dev/null 2>&1"])
        r = client.host().directory(str(ROOT_PATH / "rstudio" / f"{ubi_flavor}-{python_kernel}" / "test"))
        d = (c
             .with_directory("/test", r)
             .with_workdir("/opt/app-data")
             .with_exec(["/bin/sh", "-c", "Rscript /test/test_script.R > /dev/null 2>&1"])
             )
        await d

        # if test_script.returncode == 0:
        #     LOGGER.info("R script executed successfully!")
        #     os.unlink("test_script.R")
        # else:
        #     LOGGER.error("Error: R script failed.")
        #     fail = True
        #
        # assert not fail


def blockinfile(filename: str | pathlib.Path, contents: str, *, prefix: str = None, suffix: str = None):
    """This is similar to the function in
     * https://homely.readthedocs.io/en/latest/ref/files.html#homely-files-blockinfile-1
     * ansible.modules.lineinfile

    Not used now, but it will be useful if we want to generate "test_" function for each notebook.
    """
    begin = end = -1

    lines = open(filename, "rt").readlines()
    for line_no, line in enumerate(lines):
        if line.rstrip() == "# begin":
            begin = line_no
        elif line.rstrip() == "# end":
            end = line_no

    # todo: beautify this
    if begin == end == -1:
        lines.append("\n# begin\n")
        lines.extend(contents.splitlines(keepends=True))
        lines.append("\n# end\n")
    else:
        lines[begin:end+1] = ["# begin\n"] + contents.splitlines(keepends=True) + ["\n# end\n"]

    with open("/config.txt", "wt") as fp:
        fp.writelines(lines)


def test_line_in_file(fs: FakeFilesystem):
    fs.create_file("/config.txt", contents="hello\nworld")

    blockinfile("/config.txt", "key=value", prefix="# begin", suffix="# end")

    assert fs.get_object("/config.txt").contents == "hello\nworld\n# begin\nkey=value\n# end\n"

def test_line_in_file_2(fs: FakeFilesystem):
    fs.create_file("/config.txt", contents="hello\nworld\n# begin\nkey=value1\n# end\n")

    blockinfile("/config.txt", "key=value2", prefix="# begin", suffix="# end")

    assert fs.get_object("/config.txt").contents == "hello\nworld\n# begin\nkey=value2\n# end\n"
