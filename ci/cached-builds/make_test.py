#!/usr/bin/env python3
import argparse
import contextlib
import functools
import subprocess
import sys
import typing
import unittest
import unittest.mock

"""Runs the make commands used to deploy, test, and undeploy image in Kubernetes

The make commands this runs are intended to reproduce the commands we define in our OpenShift CI config at
https://github.com/openshift/release/blob/master/ci-operator/config/opendatahub-io/notebooks/opendatahub-io-notebooks-main.yaml#L1485
"""


class Args(argparse.Namespace):
    """Type annotation to have autocompletion for args"""

    target: str


def main() -> None:
    parser = argparse.ArgumentParser("make_test.py")
    parser.add_argument("--target", type=str)
    args = typing.cast("Args", parser.parse_args())

    run_tests(args.target)


def run_tests(target: str) -> None:
    prefix = target.translate(str.maketrans(".", "-"))
    namespace = "ns-" + prefix

    check_call(f"kubectl create namespace {namespace}", shell=True)
    check_call(f"kubectl config set-context --current --namespace={namespace}", shell=True)
    check_call(f"kubectl label namespace {namespace} fake-scc=fake-restricted-v2", shell=True)

    # wait for service account to be created, otherwise pod is refused to be created
    # $ bin/kubectl apply -k runtimes/minimal/ubi9-python-3.9/kustomize/base
    # configmap/runtime-req-config-9hhb2bhhmd created
    # Error from server (Forbidden): error when creating "runtimes/minimal/ubi9-python-3.9/kustomize/base": pods "runtime-pod" is forbidden: error looking up service account ns-runtime-minimal-ubi9-python-3-9/default: serviceaccount "default" not found
    # See https://github.com/kubernetes/kubernetes/issues/66689
    check_call("timeout 10s bash -c 'until kubectl get serviceaccount/default; do sleep 1; done'", shell=True)

    check_call(f"make deploy-{target}", shell=True)

    try:
        check_call(f"make test-{target}", shell=True)
    finally:
        # dump a lot of info to the GHA logs
        with gha_log_group("pod and statefulset info"):
            call("kubectl get statefulsets", shell=True)
            call("kubectl describe statefulsets", shell=True)
            call("kubectl get pods", shell=True)
            call("kubectl describe pods", shell=True)
            # describe does not show everything about the pod
            call("kubectl get pods -o yaml", shell=True)

        with gha_log_group("kubernetes namespace events"):
            # events aren't all that useful, but it can tell what was happening in the current namespace
            call("kubectl get events", shell=True)

        with gha_log_group("previous pod logs"):
            # relevant if the pod is crashlooping, this shows the final lines
            # use the negative label selector as a trick to match all pods (as we don't have any pods with nosuchlabel)
            call("kubectl logs --selector=nosuchlabel!=nosuchvalue --all-pods --timestamps --previous", shell=True)
        with gha_log_group("current pod logs"):
            # regular logs from a running (or finished) pod
            call("kubectl logs --selector=nosuchlabel!=nosuchvalue --all-pods --timestamps", shell=True)

    check_call(f"make undeploy-{target}", shell=True)

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
    def test_make_commands_jupyter(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("jupyter-minimal-ubi9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-jupyter-minimal-ubi9-python-3.11" in commands
        assert "make test-jupyter-minimal-ubi9-python-3.11" in commands
        assert "make undeploy-jupyter-minimal-ubi9-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_jupyter_rocm(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rocm-jupyter-tensorflow-ubi9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-rocm-jupyter-tensorflow-ubi9-python-3.11" in commands
        assert "make test-rocm-jupyter-tensorflow-ubi9-python-3.11" in commands
        assert "make undeploy-rocm-jupyter-tensorflow-ubi9-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_codeserver(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("codeserver-ubi9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-codeserver-ubi9-python-3.11" in commands
        assert "make test-codeserver-ubi9-python-3.11" in commands
        assert "make undeploy-codeserver-ubi9-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_rstudio(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rstudio-c9s-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-rstudio-c9s-python-3.11" in commands
        assert "make test-rstudio-c9s-python-3.11" in commands
        assert "make undeploy-rstudio-c9s-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_rsudio_rhel(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rstudio-rhel9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-rstudio-rhel9-python-3.11" in commands
        assert "make test-rstudio-rhel9-python-3.11" in commands
        assert "make undeploy-rstudio-rhel9-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_cuda_rstudio(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("cuda-rstudio-c9s-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-cuda-rstudio-c9s-python-3.11" in commands
        assert "make test-cuda-rstudio-c9s-python-3.11" in commands
        assert "make undeploy-cuda-rstudio-c9s-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_cuda_rstudio_rhel(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("cuda-rstudio-rhel9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-cuda-rstudio-rhel9-python-3.11" in commands
        assert "make test-cuda-rstudio-rhel9-python-3.11" in commands
        assert "make undeploy-cuda-rstudio-rhel9-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_runtime(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("runtime-datascience-ubi9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-runtime-datascience-ubi9-python-3.11" in commands
        assert "make test-runtime-datascience-ubi9-python-3.11" in commands
        assert "make undeploy-runtime-datascience-ubi9-python-3.11" in commands

    @unittest.mock.patch("make_test.execute")
    def test_make_commands_rocm_runtime(self, mock_execute: unittest.mock.Mock) -> None:
        """Compares the commands with what we had in the openshift/release yaml"""
        run_tests("rocm-runtime-pytorch-ubi9-python-3.11")
        commands: list[str] = [c[0][1][0] for c in mock_execute.call_args_list]
        assert "make deploy-rocm-runtime-pytorch-ubi9-python-3.11" in commands
        assert "make test-rocm-runtime-pytorch-ubi9-python-3.11" in commands
        assert "make undeploy-rocm-runtime-pytorch-ubi9-python-3.11" in commands


if __name__ == "__main__":
    main()
