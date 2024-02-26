import logging
import os
import re
import shlex
import subprocess
import unittest

import pytest

# test_with_papermill

"""
make jupyter-minimal-ubi9-python-3.9

# this will deploy latest tag (todays date)
$ make deploy9-jupyter-minimal-ubi9-python-3.9

$ make deploy9-jupyter-minimal-ubi9-python-3.9 NOTEBOOK_TAG=jupyter-minimal-ubi9-python-3.9-2024022
# Deploying notebook from jupyter/minimal/ubi9-python-3.9/kustomize/base directory...
bin/kubectl apply -k jupyter/minimal/ubi9-python-3.9/kustomize/base
service/jupyter-minimal-ubi9-python-3-9-notebook unchanged
statefulset.apps/jupyter-minimal-ubi9-python-3-9-notebook unchanged

$ make test-jupyter-minimal-ubi9-python-3.9
# Running tests for jupyter-minimal-ubi9-python-3-9 notebook...
# Verify the notebook's readiness by pinging the /api endpoint
bin/kubectl wait --for=condition=ready pod -l app=jupyter-minimal-ubi9-python-3-9 --timeout=600s
pod/jupyter-minimal-ubi9-python-3-9-notebook-0 condition met
bin/kubectl port-forward svc/jupyter-minimal-ubi9-python-3-9-notebook 8888:8888 & curl --retry 5 --retry-delay 5 --retry-connrefused http://localhost:8888/notebook/opendatahub/jovyan/api ; EXIT_CODE=$?; echo && pkill --full "^bin/kubectl.*port-forward.*"; \

curl: (7) Failed to connect to localhost port 8888 after 0 ms: Couldn't connect to server
Warning: Problem : connection refused. Will retry in 5 seconds. 5 retries left.
Forwarding from 127.0.0.1:8888 -> 8888
Forwarding from [::1]:8888 -> 8888
Handling connection for 8888
{"version": "2.7.3"}
# Tests notebook's functionalities 
if echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "minimal-ubi9"; then \
                bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "python3 -m pip install papermill" ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "wget https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/minimal/ubi9-python-3.9/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb minimal_ubi9_output.ipynb --kernel python3 --stderr-file minimal_ubi9_error.txt" ; if [ $? -ne 0 ]; then echo "ERROR: The minimal ubi9 notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-minimal-ubi9-python-3.9-test-e2e' directory or run 'cat minimal_ubi9_error.txt' within your container. The make process has been aborted." ; exit 1 ; fi ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat minimal_ubi9_error.txt | grep --quiet FAILED" ; if [ $? -eq 0 ]; then echo "ERROR: The minimal ubi9 notebook encountered a failure. The make process has been aborted." ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat minimal_ubi9_error.txt" ; exit 1 ; fi \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "datascience-ubi9"; then \
        make validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=jupyter-minimal-ubi9-python-3-9-notebook-0; \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "pytorch-ubi9"; then \
        make validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=jupyter-minimal-ubi9-python-3-9-notebook-0; \
                bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "python3 -m pip install papermill" ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "wget https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/pytorch/ubi9-python-3.9/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb pytorch_ubi9_output.ipynb --kernel python3 --stderr-file pytorch_ubi9_error.txt" ; if [ $? -ne 0 ]; then echo "ERROR: The pytorch ubi9 notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-pytorch-ubi9-python-3.9-test-e2e' directory or run 'cat pytorch_ubi9_error.txt' within your container. The make process has been aborted." ; exit 1 ; fi ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat pytorch_ubi9_error.txt | grep --quiet FAILED" ; if [ $? -eq 0 ]; then echo "ERROR: The pytorch ubi9 notebook encountered a failure. The make process has been aborted." ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat pytorch_ubi9_error.txt" ; exit 1 ; fi \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "tensorflow-ubi9"; then \
        make validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=jupyter-minimal-ubi9-python-3-9-notebook-0; \
                bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "python3 -m pip install papermill" ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "wget https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/tensorflow/ubi9-python-3.9/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb tensorflow_ubi9_output.ipynb --kernel python3 --stderr-file tensorflow_ubi9_error.txt" ; if [ $? -ne 0 ]; then echo "ERROR: The tensorflow ubi9 notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-tensorflow-ubi9-python-3.9-test-e2e' directory or run 'cat tensorflow_ubi9_error.txt' within your container. The make process has been aborted." ; exit 1 ; fi ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat tensorflow_ubi9_error.txt | grep --quiet FAILED" ; if [ $? -eq 0 ]; then echo "ERROR: The tensorflow ubi9 notebook encountered a failure. The make process has been aborted." ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat tensorflow_ubi9_error.txt" ; exit 1 ; fi \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "trustyai-ubi9"; then \
        make validate-ubi9-datascience -e FULL_NOTEBOOK_NAME=jupyter-minimal-ubi9-python-3-9-notebook-0; \
                bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "python3 -m pip install papermill" ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "wget https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/trustyai/ubi9-python-3.9/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb trustyai_ubi9_output.ipynb --kernel python3 --stderr-file trustyai_ubi9_error.txt" ; if [ $? -ne 0 ]; then echo "ERROR: The trustyai ubi9 notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-trustyai-ubi9-python-3.9-test-e2e' directory or run 'cat trustyai_ubi9_error.txt' within your container. The make process has been aborted." ; exit 1 ; fi ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat trustyai_ubi9_error.txt | grep --quiet FAILED" ; if [ $? -eq 0 ]; then echo "ERROR: The trustyai ubi9 notebook encountered a failure. The make process has been aborted." ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat trustyai_ubi9_error.txt" ; exit 1 ; fi \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "minimal-ubi8"; then \
                bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "python3 -m pip install papermill" ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "wget https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/minimal/ubi8-python-3.8/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb minimal_ubi8_output.ipynb --kernel python3 --stderr-file minimal_ubi8_error.txt" ; if [ $? -ne 0 ]; then echo "ERROR: The minimal ubi8 notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-minimal-ubi8-python-3.8-test-e2e' directory or run 'cat minimal_ubi8_error.txt' within your container. The make process has been aborted." ; exit 1 ; fi ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat minimal_ubi8_error.txt | grep --quiet FAILED" ; if [ $? -eq 0 ]; then echo "ERROR: The minimal ubi8 notebook encountered a failure. The make process has been aborted." ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat minimal_ubi8_error.txt" ; exit 1 ; fi \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "datascience-ubi8"; then \
        make validate-ubi8-datascience -e FULL_NOTEBOOK_NAME=jupyter-minimal-ubi9-python-3-9-notebook-0; \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "trustyai-ubi8"; then \
        make validate-ubi8-datascience -e FULL_NOTEBOOK_NAME=jupyter-minimal-ubi9-python-3-9-notebook-0; \
                bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "python3 -m pip install papermill" ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "wget https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/trustyai/ubi8-python-3.8/test/test_notebook.ipynb -O test_notebook.ipynb && python3 -m papermill test_notebook.ipynb trustyai_ubi8_output.ipynb --kernel python3 --stderr-file trustyai_ubi8_error.txt" ; if [ $? -ne 0 ]; then echo "ERROR: The trustyai ubi8 notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-trustyai-ubi8-python-3.8-test-e2e' directory or run 'cat trustyai_ubi8_error.txt' within your container. The make process has been aborted." ; exit 1 ; fi ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat trustyai_ubi8_error.txt | grep --quiet FAILED" ; if [ $? -eq 0 ]; then echo "ERROR: The trustyai ubi8 notebook encountered a failure. The make process has been aborted." ; bin/kubectl exec jupyter-minimal-ubi9-python-3-9-notebook-0 -- /bin/sh -c "cat trustyai_ubi8_error.txt" ; exit 1 ; fi \
elif echo "jupyter-minimal-ubi9-python-3-9-notebook-0" | grep -q "anaconda"; then \
        echo "There is no test notebook implemented yet for Anaconda Notebook...." \
else \
        echo "No matching condition found for jupyter-minimal-ubi9-python-3-9-notebook-0." ; \
fi
Collecting papermill
  Downloading papermill-2.5.0-py3-none-any.whl (38 kB)
Requirement already satisfied: nbformat>=5.1.2 in /opt/app-root/lib/python3.9/site-packages (from papermill) (5.9.2)
Requirement already satisfied: requests in /opt/app-root/lib/python3.9/site-packages (from papermill) (2.31.0)
Collecting click
  Downloading click-8.1.7-py3-none-any.whl (97 kB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 97.9/97.9 kB 2.9 MB/s eta 0:00:00
Collecting tenacity>=5.0.2
  Downloading tenacity-8.2.3-py3-none-any.whl (24 kB)
Collecting tqdm>=4.32.2
  Downloading tqdm-4.66.2-py3-none-any.whl (78 kB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 78.3/78.3 kB 3.2 MB/s eta 0:00:00
Requirement already satisfied: nbclient>=0.2.0 in /opt/app-root/lib/python3.9/site-packages (from papermill) (0.9.0)
Requirement already satisfied: pyyaml in /opt/app-root/lib/python3.9/site-packages (from papermill) (6.0.1)
Requirement already satisfied: entrypoints in /opt/app-root/lib/python3.9/site-packages (from papermill) (0.4)
Requirement already satisfied: traitlets>=5.4 in /opt/app-root/lib/python3.9/site-packages (from nbclient>=0.2.0->papermill) (5.14.1)
Requirement already satisfied: jupyter-core!=5.0.*,>=4.12 in /opt/app-root/lib/python3.9/site-packages (from nbclient>=0.2.0->papermill) (5.7.1)
Requirement already satisfied: jupyter-client>=6.1.12 in /opt/app-root/lib/python3.9/site-packages (from nbclient>=0.2.0->papermill) (7.4.9)
Requirement already satisfied: jsonschema>=2.6 in /opt/app-root/lib/python3.9/site-packages (from nbformat>=5.1.2->papermill) (4.21.1)
Requirement already satisfied: fastjsonschema in /opt/app-root/lib/python3.9/site-packages (from nbformat>=5.1.2->papermill) (2.19.1)
Requirement already satisfied: idna<4,>=2.5 in /opt/app-root/lib/python3.9/site-packages (from requests->papermill) (3.6)
Requirement already satisfied: urllib3<3,>=1.21.1 in /opt/app-root/lib/python3.9/site-packages (from requests->papermill) (2.2.0)
Requirement already satisfied: certifi>=2017.4.17 in /opt/app-root/lib/python3.9/site-packages (from requests->papermill) (2024.2.2)
Requirement already satisfied: charset-normalizer<4,>=2 in /opt/app-root/lib/python3.9/site-packages (from requests->papermill) (3.3.2)
Requirement already satisfied: attrs>=22.2.0 in /opt/app-root/lib/python3.9/site-packages (from jsonschema>=2.6->nbformat>=5.1.2->papermill) (23.2.0)
Requirement already satisfied: jsonschema-specifications>=2023.03.6 in /opt/app-root/lib/python3.9/site-packages (from jsonschema>=2.6->nbformat>=5.1.2->papermill) (2023.12.1)
Requirement already satisfied: referencing>=0.28.4 in /opt/app-root/lib/python3.9/site-packages (from jsonschema>=2.6->nbformat>=5.1.2->papermill) (0.33.0)
Requirement already satisfied: rpds-py>=0.7.1 in /opt/app-root/lib/python3.9/site-packages (from jsonschema>=2.6->nbformat>=5.1.2->papermill) (0.17.1)
Requirement already satisfied: python-dateutil>=2.8.2 in /opt/app-root/lib/python3.9/site-packages (from jupyter-client>=6.1.12->nbclient>=0.2.0->papermill) (2.8.2)
Requirement already satisfied: pyzmq>=23.0 in /opt/app-root/lib/python3.9/site-packages (from jupyter-client>=6.1.12->nbclient>=0.2.0->papermill) (24.0.1)
Requirement already satisfied: tornado>=6.2 in /opt/app-root/lib/python3.9/site-packages (from jupyter-client>=6.1.12->nbclient>=0.2.0->papermill) (6.4)
Requirement already satisfied: nest-asyncio>=1.5.4 in /opt/app-root/lib/python3.9/site-packages (from jupyter-client>=6.1.12->nbclient>=0.2.0->papermill) (1.6.0)
Requirement already satisfied: platformdirs>=2.5 in /opt/app-root/lib/python3.9/site-packages (from jupyter-core!=5.0.*,>=4.12->nbclient>=0.2.0->papermill) (4.2.0)
Requirement already satisfied: six>=1.5 in /opt/app-root/lib/python3.9/site-packages (from python-dateutil>=2.8.2->jupyter-client>=6.1.12->nbclient>=0.2.0->papermill) (1.16.0)
Installing collected packages: tqdm, tenacity, click, papermill
Successfully installed click-8.1.7 papermill-2.5.0 tenacity-8.2.3 tqdm-4.66.2

[notice] A new release of pip available: 22.2.2 -> 24.0
[notice] To update, run: pip install --upgrade pip
--2024-02-23 07:49:19--  https://raw.githubusercontent.com/opendatahub-io/notebooks/main/jupyter/minimal/ubi9-python-3.9/test/test_notebook.ipynb
Resolving raw.githubusercontent.com (raw.githubusercontent.com)... 185.199.108.133, 185.199.111.133, 185.199.110.133, ...
Connecting to raw.githubusercontent.com (raw.githubusercontent.com)|185.199.108.133|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 1822 (1.8K) [text/plain]
Saving to: ‘test_notebook.ipynb’

     0K .                                                     100% 45.8M=0s

2024-02-23 07:49:20 (45.8 MB/s) - ‘test_notebook.ipynb’ saved [1822/1822]

Input Notebook:  test_notebook.ipynb
Output Notebook: minimal_ubi9_output.ipynb
Notebook JSON is invalid: Additional properties are not allowed ('id' was unexpected)

Failed validating 'additionalProperties' in code_cell:

On instance['cells'][0]:
{'cell_type': 'code',
 'execution_count': None,
 'id': '2d972b6b-1211-4c21-a7e8-a1683b72a62c',
 'metadata': {},
 'outputs': ['...0 outputs...'],
 'source': 'import unittest\n'
           'import jupyterlab as jp\n'
           'from platform import pyt...'}
Executing:   0%|          | 0/1 [00:00<?, ?cell/s]Executing notebook with kernel: python3
Executing: 100%|██████████| 1/1 [00:02<00:00,  2.59s/cell]
command terminated with exit code 1

make validate-runtime-image image=quay.io/opendatahub/workbench-images:base-ubi9-python-3.9-2023b_20240223


"""

import pathlib
ROOT_PATH = pathlib.Path(__file__).absolute().parent.parent

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT = 10 * 60

# import setuptools.set

def run_kubectl(args: list[str], check=True, background=False, stdout=None, stderr=None) -> subprocess.Popen | subprocess.CompletedProcess:
    return run_command([str(ROOT_PATH / 'bin/kubectl')] + args, check=check, background=background, stdout=stdout, stderr=stderr)


def run_command(args: list[str], check=True, background=False, stdout=None, stderr=None):
    p = subprocess.Popen(args, text=True, stdout=stdout, stderr=stderr)
    LOGGER.info(f"Running command: {shlex.join(args)}")
    if background:
        return p
    stdout, stderr = p.communicate(timeout=COMMAND_TIMEOUT)
    if stdout:
        LOGGER.debug(f"Command output: {stdout}")
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, shlex.join(args), stdout, stderr)
    return subprocess.CompletedProcess(args, p.returncode, stdout, stderr)


class Substring(str):
    """
    >>> match Substring("abrakadabra"):
    >>> ...  case "raka":  # matches
    """
    __eq__ = str.__contains__

def test_jupyter_minimal_ubi9_python_3_9():
    test_notebook(notebook_name="jupyter-minimal-ubi9-python-3.9")

def test_jupyter_datascience_ubi9_python_3_9():
    test_notebook(notebook_name="jupyter-datascience-ubi9-python-3.9")

def test_notebook(notebook_name) -> None:
    notebook_name = notebook_name.replace("cuda-", "").replace(".", "-")
    LOGGER.info("# Running tests for $(NOTEBOOK_NAME) notebook...")
    # Verify the notebook's readiness by pinging the /api endpoint
    run_kubectl(["wait", "--for=condition=ready", "pod", "-l", f"app={notebook_name}", "--timeout=600s"])
    with run_kubectl(["port-forward", f"svc/{notebook_name}-notebook", "8888:8888"], background=True) as p:
        run_command(["curl", "--retry", "25", "--retry-delay", "1", "--retry-connrefused",
                     "http://localhost:8888/notebook/opendatahub/jovyan/api"])
        p.kill()
    full_notebook_name = run_kubectl(["get", "pods", "-l", f"app={notebook_name}", "-o", "custom-columns=:metadata.name"], stdout=subprocess.PIPE).stdout.strip()

    match Substring(full_notebook_name):
        case "minimal-ubi9":
            test_with_papermill(full_notebook_name, "minimal", "ubi9", "python-3.9")
        case "datascience-ubi9":
            validate_ubi9_datascience(full_notebook_name)
        case "pytorch-ubi9":
            validate_ubi9_datascience(full_notebook_name)
            test_with_papermill("pytorch", "ubi9", "python-3.9")
        case "tensorflow-ubi9":
            validate_ubi9_datascience(full_notebook_name)
            test_with_papermill("tensorflow", "ubi9", "python-3.9")
        case "trustyai-ubi9":
            validate_ubi9_datascience(full_notebook_name)
            test_with_papermill("trustyai", "ubi9", "python-3.9")
        case "minimal-ubi8":
            test_with_papermill("minimal", "ubi8", "python-3.8")
        case "datascience-ubi8":
            validate_ubi8_datascience(full_notebook_name)
        case "trustyai-ubi8":
            validate_ubi8_datascience(full_notebook_name)
            test_with_papermill("trustyai", "ubi8", "python-3.8")
        case "anaconda":
            print("There is no test notebook implemented yet for Anaconda Notebook....")
        case _:
            print(f"No matching condition found for {full_notebook_name}.")


# def test_with_tenacity() -> None:

NOTEBOOK_REPO_BRANCH_BASE = os.environ.get("NOTEBOOK_REPO_BRANCH_BASE") or "https://raw.githubusercontent.com/opendatahub-io/notebooks/main"
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
def test_with_papermill(full_notebook_name, notebook_name, ubi_flavor, python_kernel):
    run_kubectl(['exec', full_notebook_name, '--', '/bin/sh', "-c", "python3 -m pip install papermill"])
    r = run_kubectl(['exec', full_notebook_name, '--', '/bin/sh', "-c",
                 f"wget {NOTEBOOK_REPO_BRANCH_BASE}/jupyter/{notebook_name}/{ubi_flavor}-{python_kernel}/test/test_notebook.ipynb -O test_notebook.ipynb"
                 f" && python3 -m papermill test_notebook.ipynb {notebook_name}_{ubi_flavor}_output.ipynb --kernel python3 --stderr-file {notebook_name}_{ubi_flavor}_error.txt"], check=False)
    if r.returncode != 0:
        LOGGER.error(f"ERROR: The {notebook_name} {ubi_flavor} notebook encountered a failure."
                     f" To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-$(1)-$(2)-$(3)-test-e2e' directory or run 'cat $(1)_$(2)_error.txt' within your container."
                     f" The make process has been aborted.")
        assert False
    else:
        r = run_kubectl(["exec", full_notebook_name, "--", "/bin/sh", "-c", f"cat {notebook_name}_{ubi_flavor}_error.txt | grep --quiet FAILED"], check=False)
        if r.returncode == 0:
            LOGGER.error(f"ERROR: The {notebook_name} {ubi_flavor} notebook encountered a failure. The make process has been aborted.")
            run_kubectl(["exec", full_notebook_name, "--", "/bin/sh", "-c", f"cat {notebook_name}_{ubi_flavor}_error.txt"])
            assert False


def validate_ubi9_datascience(full_notebook_name):
    test_with_papermill(full_notebook_name, "minimal", "ubi9", "python-3.9")
    test_with_papermill(full_notebook_name, "datascience", "ubi9", "python-3.9")

def validate_ubi8_datascience(full_notebook_name):
    test_with_papermill(full_notebook_name,"minimal","ubi8","python-3.8")
    test_with_papermill(full_notebook_name,"datascience","ubi8","python-3.8")

def test_validate_runtime_image():
    LOGGER.info("# Running tests for $(NOTEBOOK_NAME) runtime...")
    run_kubectl(["wait", "--for=condition=ready", "pod", "runtime-pod", "--timeout=300s"])
    LOGGER.error("Usage: make validate-runtime-image image=<container-image-name>")
    fail = False
    for cmd in REQUIRED_RUNTIME_IMAGE_COMMANDS:
        LOGGER.info("=> Checking container image $$image for $$cmd...")
        r = run_kubectl(["exec", f"runtime-pod", "which {cmd} > /dev/null 2>&1"], check=False)
        if r.returncode != 0:
            LOGGER.error("ERROR: Container image $$image  does not meet criteria for command: $$cmd")
            fail = True
            continue
        if cmd == "python3":
            LOGGER.info("=> Checking notebook execution...")
            r = run_kubectl(["exec", "runtime-pod", "/bin/sh", "-c", "python3 -m pip install -r /opt/app-root/elyra/requirements-elyra.txt"
                                                                 " && curl https://raw.githubusercontent.com/nteract/papermill/main/papermill/tests/notebooks/simple_execute.ipynb --output simple_execute.ipynb"
                                                                 " && python3 -m papermill simple_execute.ipynb output.ipynb > /dev/null"], check=False)
            if r.returncode != 0:
                LOGGER.error("ERROR: Image does not meet Python requirements criteria in requirements-elyra.txt")
                fail = True
    assert not fail, "=> ERROR: Container image $$image is not a suitable Elyra runtime image"
    LOGGER.info(f"=> Container image {image} is a suitable Elyra runtime image")

def test_validate_codeserver_image():
    codeserver_pod_ready = run_kubectl(
        ["wait", "--for=condition=ready", "pod", "codeserver-pod", "--timeout=300s"], check=False)
    assert codeserver_pod_ready.returncode == 0, "Code-server pod did not become ready within expected time"

    assert image, "Usage: make validate-codeserver-image image=<container-image-name>"

    for cmd in REQUIRED_CODE_SERVER_IMAGE_COMMANDS:
        result = run_kubectl(["exec", "codeserver-pod", f"which {cmd} > /dev/null 2>&1"], check=False)
        assert result.returncode == 0, f"ERROR: Container image {image} does not meet criteria for command: {cmd}"

def validate_rstudio_image():
    # $(eval NOTEBOOK_NAME := $(subst .,-,$(subst cuda-,,$*)))
    LOGGER.info("# Running tests for $(NOTEBOOK_NAME) RStudio Server image...")
    rstudo_pod_ready = run_kubectl(["wait", "--for=condition=ready", "pod", "rstudio-pod", "--timeout=300s"], check=False)
    assert rstudo_pod_ready.returncode == 0, "Code-server pod did not become ready within expected time"
    assert image, "Usage: make validate-rstudio-image image=<container-image-name>"

    LOGGER.info("=> Checking container image $$image for package intallation...")
    run_kubectl(["exec", "-it", "rstudio-pod", "--", "mkdir -p /opt/app-root/src/R/temp-library > /dev/null 2>&1"])
    tinytex_install = run_kubectl(["exec", "rstudio-pod", "--", '''R -e "install.packages('tinytex', lib='/opt/app-root/src/R/temp-library')" > /dev/null 2>&1'''], check=False)
    if tinytex_install.returncode == 0:
        LOGGER.info("Tinytex installation successful!")
    else:
        LOGGER.error("Error: Tinytex installation failed.")
        assert False

    fail = False
    for cmd in REQUIRED_R_STUDIO_IMAGE_COMMANDS:
        LOGGER.info(f"=> Checking container image {image} for {cmd}...")
        which_cmd = run_kubectl(["exec", "rstudio-pod", f"which {cmd} > /dev/null 2>&1"], check=False)
        if which_cmd.returncode == 0:
            LOGGER.info(f"{cmd} executed successfully!")
        else:
            LOGGER.error("ERROR: Container image {image}  does not meet criteria for command: {cmd}")
            fail = True
            continue

    LOGGER.info("=> Fetching R script from URL and executing on the container...")
    run_command(["curl", "-sSL", "-o", "test_script.R" f"{NOTEBOOK_REPO_BRANCH_BASE}/rstudio/c9s-python-3.9/test/test_script.R"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_kubectl(["cp", "test_script.R", "rstudio-pod:/opt/app-root/src/test_script.R"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    test_script = run_kubectl(["exec", "rstudio-pod", "--", "Rscript /opt/app-root/src/test_script.R > /dev/null 2>&1"])
    if test_script.returncode == 0:
        LOGGER.info("R script executed successfully!")
        os.unlink("test_script.R")
    else:
        LOGGER.error("Error: R script failed.")
        fail = True

    assert not fail


def test_build_images():
    for dockerfile in ROOT_PATH.glob("**/Dockerfile"):
        print(dockerfile)

def test_build_makefile():
    image_targets = []
    for line in open("/home/jdanek/repos/notebooks/Makefile"):
        if line[0] in (" ", "\t"):
            continue
        split_comment = line.split("#", maxsplit=1)
        content = split_comment[0]
        if not content:
            continue

        m = re.search(r"^([-.A-Za-z0-9]+):", content)
        if not m:
            continue
        target = m.group(1)
        if target == ".PHONY":
            continue
        if not any(target.startswith(s) for s in ("jupyter", "cuda", "habana", "runtime", "base", "rstudio")):
            continue

        image_targets.append(target)

    generate_launchers(image_targets)

def generate_launchers(targets: list[str]):
    with open(ROOT_PATH / "tests" / "launcher.py", "wt") as fp:
        print("import tests.notebook_tests", file=fp)
        for target in targets:
            target_py = target.replace(".", "_").replace("-", "_")
            # language=python
            print(f"""
def test_{target_py}_launcher():
    from .notebook_tests import run_command
    run_command(["make", "{target}"])
""", file=fp)
        # print("tests.notebook_tests.test_jupyter_minimal_ubi9_python_3_9()")
        # print("tests.notebook_tests.test_jupyter_datascience_ubi9_python_3_9()")


"""

#

#
#
# from papermill import execute_notebook
#
# def test_with_papermill():
#     execute_notebook(
#         input_path='notebook.ipynb',
#         output_path='output.ipynb'
#     )
#
# validate-ubi9-datascience
#
# validate-ubi8-datascience
#
# validate-runtime-image
#
# validate-codeserver-image
#
# deploy, undeploy?
#
# k8s and docker?
"""
