#!/usr/bin/env python3
import argparse
import contextlib
import functools
import re
import subprocess
import sys
import time
import typing
import unittest
import unittest.mock

"""Runs the make commands used to deploy, test, and undeploy image in Kubernetes

The make commands this runs are intended to reproduce the commands we define in our OpenShift CI config at
https://github.com/openshift/release/blob/master/ci-operator/config/opendatahub-io/notebooks/opendatahub-io-notebooks-main.yaml#L1485
https://github.com/openshift/release/commit/24b4dafa1cfc7bf3652b625fb1759d6db73c4b98
"""


class Args(argparse.Namespace):
    """Type annotation to have autocompletion for args"""
    target: str


def main() -> None:
    parser = argparse.ArgumentParser("make_test.py")
    parser.add_argument("--target", type=str)
    args = typing.cast(Args, parser.parse_args())

    run_tests(args.target)


def run_tests(target: str) -> None:
    prefix = target.translate(str.maketrans(".", "-"))
    # this is a pod name in statefulset, some tests deploy individual unmanaged pods, though
    pod = prefix + "-notebook-0"  # `$(kubectl get statefulset -o name | head -n 1)` would work too
    namespace = "ns-" + prefix

    py = target[-1]
    assert py in ('8', '9'), target

    if target.startswith("runtime-"):
        deploy = f"deploy{py}"
        deploy_target = target.replace("runtime-", "runtimes-")
    elif target.startswith("intel-runtime-"):
        deploy = f"deploy{py}"
        deploy_target = target.replace("intel-runtime-", "intel-runtimes-")
    elif target.startswith("rocm-runtime-"):
        deploy = f"deploy{py}"
        deploy_target = target.replace("rocm-runtime-", "runtimes-rocm-")
    elif target.startswith("rocm-jupyter-"):
        deploy = f"deploy{py}"
        deploy_target = target.replace("rocm-jupyter-", "jupyter-rocm-")
    elif target.startswith("cuda-rstudio-"):
        deploy = f"deploy"
        os = re.match(r"^cuda-rstudio-([^-]+-).*", target)
        deploy_target = os.group(1) + target.removeprefix("cuda-")
    elif target.startswith("rstudio-"):
        deploy = "deploy"
        os = re.match(r"^rstudio-([^-]+-).*", target)
        deploy_target = os.group(1) + target
    else:
        deploy = f"deploy{py}"
        deploy_target = target

    check_call(f"kubectl create namespace {namespace}", shell=True)
    check_call(f"kubectl config set-context --current --namespace={namespace}", shell=True)
    check_call(f"kubectl label namespace {namespace} fake-scc=fake-restricted-v2", shell=True)

    # wait for service account to be created, otherwise pod is refused to be created
    # $ bin/kubectl apply -k runtimes/minimal/ubi9-python-3.9/kustomize/base
    # configmap/runtime-req-config-9hhb2bhhmd created
    # Error from server (Forbidden): error when creating "runtimes/minimal/ubi9-python-3.9/kustomize/base": pods "runtime-pod" is forbidden: error looking up service account ns-runtime-minimal-ubi9-python-3-9/default: serviceaccount "default" not found
    # See https://github.com/kubernetes/kubernetes/issues/66689
    check_call(f"timeout 10s bash -c 'until kubectl get serviceaccount/default; do sleep 1; done'", shell=True)

    check_call(f"make {deploy}-{deploy_target}", shell=True)
    wait_for_stability(pod)

    try:
        if target.startswith("runtime-") or target.startswith("intel-runtime-"):
            check_call(f"make validate-runtime-image image={target}", shell=True)
        elif target.startswith("rocm-runtime-"):
            check_call(f"make validate-runtime-image image={target
                       .replace("rocm-runtime-", "runtime-rocm-")}", shell=True)
        elif target.startswith("rstudio-") or target.startswith("cuda-rstudio-"):
            check_call(f"make validate-rstudio-image image={target}", shell=True)
        elif target.startswith("codeserver-"):
            check_call(f"make validate-codeserver-image image={target}", shell=True)
        elif target.startswith("rocm-jupyter"):
            check_call(f"make test-{target
                       .replace("rocm-jupyter-", "jupyter-rocm-")}", shell=True)
        else:
            check_call(f"make test-{target}", shell=True)
    finally:
        # dump a lot of info to the GHA logs
        with gha_log_group("pod and statefulset info"):
            call(f"kubectl get statefulsets", shell=True)
            call(f"kubectl describe statefulsets", shell=True)
            call(f"kubectl get pods", shell=True)
            call(f"kubectl describe pods", shell=True)
            # describe does not show everything about the pod
            call(f"kubectl get pods -o yaml", shell=True)

        with gha_log_group("kubernetes namespace events"):
            # events aren't all that useful, but it can tell what was happening in the current namespace
            call(f"kubectl get events", shell=True)

        with gha_log_group("previous pod logs"):
            # relevant if the pod is crashlooping, this shows the final lines
            # use the negative label selector as a trick to match all pods (as we don't have any pods with nosuchlabel)
            call(f"kubectl logs --selector=nosuchlabel!=nosuchvalue --all-pods --timestamps --previous", shell=True)
        with gha_log_group("current pod logs"):
            # regular logs from a running (or finished) pod
            call(f"kubectl logs --selector=nosuchlabel!=nosuchvalue --all-pods --timestamps", shell=True)

    check_call(f"make un{deploy}-{deploy_target}", shell=True)

    print(f"[INFO] Finished testing {target}")


@functools.wraps(subprocess.check_call)
def check_call(*args, **kwargs) -> int:
    return execute(subprocess.check_call, args, kwargs)


@functools.wraps(subprocess.call)
def call(*args, **kwargs) -> int:
    return execute(subprocess.call, args, kwargs)


def execute(executor: typing.Callable, args: tuple, kwargs: dict) -> int:
    print(f"[INFO] Running command {args, kwargs}")
    sys.stdout.flush()
    result = executor(*args, **kwargs)
    print(f"\tDONE running command {args, kwargs}")
    sys.stdout.flush()
    return result


# TODO(jdanek) this is a dumb impl, needs to be improved
def wait_for_stability(pod: str) -> None:
    """Waits for the pod to be stable. Often I'm seeing that the probes initially fail.
    > error: Internal error occurred: error executing command in container: container is not created or running
    > error: unable to upgrade connection: container not found ("notebook")
    """
    timeout = 100
    for _ in range(3):
        call(
            f"timeout {timeout}s bash -c 'until kubectl wait --for=condition=Ready pods --all --timeout 5s; do sleep 1; done'", shell=True)
        timeout = 50
        time.sleep(3)


# https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#grouping-log-lines
@contextlib.contextmanager
def gha_log_group(title):
    """Prints the starting and ending magic strings for GitHub Actions line group in log."""
    print(f"::group::{title}", file=sys.stdout)
    sys.stdout.flush()
    try:
        yield
    finally:
        print("::endgroup::", file=sys.stdout)
        sys.stdout.flush()


# https://docs.python.org/3/library/unittest.mock-examples.html#patch-decorators
@unittest.mock.patch("time.sleep", unittest.mock.Mock())
class TestMakeTest(unittest.TestCase):
    @unittest.mock.patch("make_test.execute")
    def test_make_commands_jupyter_py38(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("jupyter-minimal-ubi9-python-3.8")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy8-jupyter-minimal-ubi9-python-3.8" in commands
        assert "make test-jupyter-minimal-ubi9-python-3.8" in commands
        assert "make undeploy8-jupyter-minimal-ubi9-python-3.8" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_jupyter_py39(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("jupyter-minimal-ubi9-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy9-jupyter-minimal-ubi9-python-3.9" in commands
        assert "make test-jupyter-minimal-ubi9-python-3.9" in commands
        assert "make undeploy9-jupyter-minimal-ubi9-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_jupyter_rocm(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rocm-jupyter-tensorflow-ubi9-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy9-jupyter-rocm-tensorflow-ubi9-python-3.9" in commands
        assert "make test-jupyter-rocm-tensorflow-ubi9-python-3.9" in commands
        assert "make undeploy9-jupyter-rocm-tensorflow-ubi9-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_codeserver(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("codeserver-ubi9-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy9-codeserver-ubi9-python-3.9" in commands
        assert "make validate-codeserver-image image=codeserver-ubi9-python-3.9" in commands
        assert "make undeploy9-codeserver-ubi9-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_rstudio(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rstudio-c9s-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-c9s-rstudio-c9s-python-3.9" in commands
        assert "make validate-rstudio-image image=rstudio-c9s-python-3.9" in commands
        assert "make undeploy-c9s-rstudio-c9s-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_cuda_rstudio(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("cuda-rstudio-c9s-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        print(commands)
        assert "make deploy-c9s-rstudio-c9s-python-3.9" in commands
        assert "make validate-rstudio-image image=cuda-rstudio-c9s-python-3.9" in commands
        assert "make undeploy-c9s-rstudio-c9s-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_runtime_py38(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("runtime-datascience-ubi8-python-3.8")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy8-runtimes-datascience-ubi8-python-3.8" in commands
        assert "make validate-runtime-image image=runtime-datascience-ubi8-python-3.8" in commands
        assert "make undeploy8-runtimes-datascience-ubi8-python-3.8" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_runtime_py39(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("runtime-datascience-ubi9-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy9-runtimes-datascience-ubi9-python-3.9" in commands
        assert "make validate-runtime-image image=runtime-datascience-ubi9-python-3.9" in commands
        assert "make undeploy9-runtimes-datascience-ubi9-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_intel_runtime(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("intel-runtime-ml-ubi9-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy9-intel-runtimes-ml-ubi9-python-3.9" in commands
        assert "make validate-runtime-image image=intel-runtime-ml-ubi9-python-3.9" in commands
        assert "make undeploy9-intel-runtimes-ml-ubi9-python-3.9" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_rocm_runtime(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rocm-runtime-pytorch-ubi9-python-3.9")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy9-runtimes-rocm-pytorch-ubi9-python-3.9" in commands
        assert "make validate-runtime-image image=runtime-rocm-pytorch-ubi9-python-3.9" in commands
        assert "make undeploy9-runtimes-rocm-pytorch-ubi9-python-3.9" in commands


if __name__ == "__main__":
    main()
