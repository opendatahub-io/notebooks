from __future__ import annotations

import binascii
import functools
import inspect
import json
import io
import logging
import pathlib
import re
import tempfile
import textwrap
import threading
from typing import TYPE_CHECKING, Any, Callable

import pytest
import requests
import testcontainers.core.container
import testcontainers.core.waiting_utils

import kubernetes
import kubernetes.dynamic.exceptions
import kubernetes.stream.ws_client
import kubernetes.client.api.core_v1_api

import ocp_resources.pod
import ocp_resources.deployment
import ocp_resources.service
import ocp_resources.persistent_volume_claim
import ocp_resources.project_request
import ocp_resources.namespace
import ocp_resources.project_project_openshift_io

import yaml
import time

from tests.containers import docker_utils, socket_proxy
from tests.containers import kubernetes_utils

import pytest

from tests.containers.kubernetes_utils import TestFrame, PodUtils
from tests.containers.socket_proxy import SubprocessProxy

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pytest_subtests


TIMEOUT_2MIN = 2 * 60

@functools.wraps(ocp_resources.namespace.Namespace.__init__)
def create_namespace(privileged_client: bool = False, *args, **kwargs) -> ocp_resources.project_project_openshift_io.Project:
    if not privileged_client:
        with ocp_resources.project_request.ProjectRequest(*args, **kwargs):
            project = ocp_resources.project_project_openshift_io.Project(*args, **kwargs)
            project.wait_for_status(status=project.Status.ACTIVE, timeout=TIMEOUT_2MIN)
            return project
    else:
        with ocp_resources.namespace.Namespace(*args, **kwargs) as ns:
            ns.wait_for_status(status=ocp_resources.namespace.Namespace.Status.ACTIVE, timeout=TIMEOUT_2MIN)
            return ns


class ImageDeployment:
    def __init__(self, client: kubernetes.dynamic.DynamicClient, image: str):
        self.client = client
        self.image = image
        self.tf = TestFrame()

    def __enter__(self) -> ImageDeployment:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tf.destroy()

    def deploy(self, container_name: str) -> None:
        LOGGER.debug(f"Deploying {self.image}")
        # custom namespace is necessary, because we cannot assign a SCC to pods created in one of the default namespaces:
        #  default, kube-system, kube-public, openshift-node, openshift-infra, openshift.
        # https://docs.openshift.com/container-platform/4.17/authentication/managing-security-context-constraints.html#role-based-access-to-ssc_configuring-internal-oauth

        ns = create_namespace(privileged_client=False, name="jdanek2")
        self.tf.push(ns)

        pvc = ocp_resources.persistent_volume_claim.PersistentVolumeClaim(
            name=container_name,
            namespace=ns.name,
            accessmodes=ocp_resources.persistent_volume_claim.PersistentVolumeClaim.AccessMode.RWO,
            volume_mode=ocp_resources.persistent_volume_claim.PersistentVolumeClaim.VolumeMode.FILE,
            size="1Gi",
        )
        self.tf.push(pvc, wait=True)
        deployment = ocp_resources.deployment.Deployment(
            client=self.client,
            name=container_name,
            namespace=ns.name,
            selector={"matchLabels": {"app": container_name}},
            replicas=1,
            template={
                "metadata": {
                    "annotations": {
                        # This will result in the container spec having something like below,
                        # regardless of what kind of namespace this is being run in.
                        # For example, `default` is a privileged ns.
                        # ```
                        # spec:
                        #   securityContext:
                        #     seLinuxOptions:
                        #       level: 's0:c34,c4'
                        #     fsGroup: 1001130000
                        #     seccompProfile:
                        #       type: RuntimeDefault
                        # ```
                        "openshift.io/scc": "restricted-v2"
                    },
                    "labels": {
                        "app": container_name,
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "image": self.image,
                            # "command": ["/bin/sh", "-c", "while true ; do date; sleep 5; done;"],
                            "ports": [
                                {
                                    "containerPort": 8888,
                                    "name": "notebook-port",
                                    "protocol": "TCP",
                                }
                            ],
                            # rstudio will not start without its volume mount and it does not log the error for it
                            # see the testcontainers implementation of this (the tty=True part)
                            "volumeMounts": [
                                {
                                    "mountPath": "/opt/app-root/src",
                                    "name": "my-workbench"
                                }
                            ],
                        },
                    ],
                    "volumes": [
                        {
                            "name": "my-workbench",
                            "persistentVolumeClaim": {
                                "claimName": container_name,
                            }
                        }
                    ]
                }
            }
        )
        self.tf.push(deployment)
        LOGGER.debug(f"Waiting for pods to become ready...")
        PodUtils.wait_for_pods_ready(self.client, namespace_name=ns.name, label_selector=f"app={container_name}",
                                     expect_pods_count=1)
        # ocp_resources.service.Service(
        #     name=container_name,
        #     namespace="default",
        #     labels={"app": container_name},
        #     type=ocp_resources.service.Service.Type.ClusterIP,
        #     selector={"app": container_name},
        #     ports=[
        #         {
        #             "port": 8888,
        #             "targetPort": "notebook-port"
        #         }
        #     ],
        # )

        # sample code from
        # https://github.com/kubernetes-client/python/blob/master/examples/pod_portforward.py

        core_v1_api = kubernetes.client.api.core_v1_api.CoreV1Api(api_client=self.client.client)
        pod_name: kubernetes.client.models.v1_pod_list.V1PodList = core_v1_api.list_namespaced_pod(
            namespace=ns.name,
            label_selector=f"app={container_name}"
        )
        assert len(pod_name.items) == 1
        pod: kubernetes.client.models.v1_pod.V1Pod = pod_name.items[0]

        p = socket_proxy.SocketProxy("localhost", 0, core_v1_api, pod)
        t = threading.Thread(target=p.start)
        t.start()
        port = p.get_actual_port()
        LOGGER.debug(f"Listening on port {port}")
        resp = requests.get(f"http://localhost:{port}")
        assert resp.status_code == 200
        LOGGER.debug(f"Done with portforward")

        self.tf.add(p.cancellation_token, lambda t: t.cancel())


def create_session_with_socket(sock):
    session = requests.Session()
    adapter = CustomAdapter(socket=sock)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

class TestBaseImage:
    """Tests that are applicable for all images we have in this repository."""

    def test_elf_files_can_link_runtime_libs(self, subtests: pytest_subtests.SubTests, image):
        container = testcontainers.core.container.DockerContainer(image=image, user=0, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")

        def check_elf_file():
            """This python function will be executed on the image itself.
            That's why it has to have here all imports it needs."""
            import glob
            import os
            import json
            import subprocess
            import stat

            dirs = [
                "/bin",
                "/lib",
                "/lib64",
                "/opt/app-root"
            ]
            for path in dirs:
                count_scanned = 0
                unsatisfied_deps: list[tuple[str, str]] = []
                for dlib in glob.glob(os.path.join(path, "**"), recursive=True):
                    # we will visit all files eventually, no need to bother with symlinks
                    s = os.stat(dlib, follow_symlinks=False)
                    isdirectory = stat.S_ISDIR(s.st_mode)
                    isfile = stat.S_ISREG(s.st_mode)
                    executable = bool(s.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
                    if isdirectory or not executable or not isfile:
                        continue
                    with open(dlib, mode='rb') as fp:
                        magic = fp.read(4)
                    if magic != b'\x7fELF':
                        continue

                    count_scanned += 1
                    ld_library_path = os.environ.get("LD_LIBRARY_PATH", "") + os.path.pathsep + os.path.dirname(dlib)
                    output = subprocess.check_output(["ldd", dlib],
                                                     # search the $ORIGIN, essentially; most python libs expect this
                                                     env={**os.environ, "LD_LIBRARY_PATH": ld_library_path},
                                                     text=True)
                    for line in output.splitlines():
                        if "not found" in line:
                            unsatisfied_deps.append((dlib, line.strip()))
                    assert output
                print("OUTPUT>",
                      json.dumps({"dir": path, "count_scanned": count_scanned, "unsatisfied": unsatisfied_deps}))

        try:
            container.start()
            ecode, output = container.exec(
                encode_python_function_execution_command_interpreter("/usr/bin/python3", check_elf_file))
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

        for line in output.decode().splitlines():
            logging.debug(line)
            if not line.startswith("OUTPUT> "):
                continue
            data = json.loads(line[len("OUTPUT> "):])
            assert data['count_scanned'] > 0
            for dlib, deps in data["unsatisfied"]:
                # here goes the allowlist
                if re.search(r"^/lib64/python3.\d+/site-packages/hawkey/test/_hawkey_test.so", dlib) is not None:
                    continue  # this is some kind of self test or what
                if re.search(r"^/lib64/systemd/libsystemd-core-\d+.so", dlib) is not None:
                    continue  # this is expected and we don't use systemd anyway
                if deps.startswith("libodbc.so.2"):
                    continue  # todo(jdanek): known issue RHOAIENG-18904
                if deps.startswith("libcuda.so.1"):
                    continue  # cuda magic will mount this into /usr/lib64/libcuda.so.1 and it will be found
                if deps.startswith("libjvm.so"):
                    continue  # it's in ../server
                if deps.startswith("libtracker-extract.so"):
                    continue  # it's in ../

                with subtests.test(f"{dlib=}"):
                    pytest.fail(f"{dlib=} has unsatisfied dependencies {deps=}")

    def test_oc_command_runs(self, image: str):
        client = kubernetes_utils.get_client()
        print(client)

        username = kubernetes_utils.get_username(client)
        print(username)

        with ImageDeployment(client, image) as image:
            image.deploy("some-container")

        return

        # kont = kubernetes.client.models.v1_container.V1Container()
        # deployment = ocp_resources.deployment.Deployment(client=client, name="some-deployment", namespace="default",
        #                                                  selector={"matchLabels": {"app": "nginx"}},
        #                                                  template=yaml.safe_load(io.StringIO("""
        # metadata:
        #   labels:
        #     app: nginx
        # spec:
        #   containers:
        #   - name: nginx
        #     image: nginx:1.14.2
        #     ports:
        #     - containerPort: 80
        # """)))

        container_name = "nginx"
        deployment = ocp_resources.deployment.Deployment(client=client, yaml_file=io.StringIO(
            # language=yaml
            f"""
# no nk8s
apiVersion: apps/v1
kind: Deployment
metadata:
  namespace: default
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: {container_name}
        image: nginx:1.14.2
        ports:
        - containerPort: 80
"""))

        print(deployment)
        with kubernetes_utils.TestFrame() as tf:
            tf.push(deployment, wait=True)

            pods = list(ocp_resources.pod.Pod.get(namespace="default", label_selector="app=nginx"))
            assert len(pods) == 3
            kubernetes_utils.PodUtils.wait_for_pods_ready(client, "default",
                                                          label_selector="app=nginx", expect_pods_count=3)

        container = testcontainers.core.container.DockerContainer(image=image, user=23456, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")
        try:
            container.start()
            ecode, output = container.exec(["/bin/sh", "-c", "oc version"])
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

        logging.debug(output.decode())
        assert ecode == 0

    # @pytest.mark.environmentss("docker")
    def test_oc_command_runs_fake_fips(self, image: str, subtests: pytest_subtests.SubTests):
        """Establishes a best-effort fake FIPS environment and attempts to execute `oc` binary in it.

        Related issue: RHOAIENG-4350 In workbench the oc CLI tool cannot be used on FIPS enabled cluster"""
        with tempfile.TemporaryDirectory() as tmp_crypto:
            # Ubuntu does not even have /proc/sys/crypto directory, unless FIPS is activated and machine
            #  is rebooted, see https://ubuntu.com/security/certifications/docs/fips-enablement
            # NOTE: mounting a temp file as `/proc/sys/crypto/fips_enabled` is further discussed in
            #  * https://issues.redhat.com/browse/RHOAIENG-4350
            #  * https://github.com/junaruga/fips-mode-user-space/blob/main/fips-mode-user-space-setup
            tmp_crypto = pathlib.Path(tmp_crypto)
            (tmp_crypto / 'crypto').mkdir()
            (tmp_crypto / 'crypto' / 'fips_enabled').write_text("1\n")
            (tmp_crypto / 'crypto' / 'fips_name').write_text("Linux Kernel Cryptographic API\n")
            (tmp_crypto / 'crypto' / 'fips_version').write_text("6.10.10-200.fc40.aarch64\n")
            # tmpdir is by-default created with perms restricting access to user only
            tmp_crypto.chmod(0o777)

            container = testcontainers.core.container.DockerContainer(image=image, user=54321, group_add=[0])
            container.with_volume_mapping(str(tmp_crypto), "/proc/sys", mode="ro,z")
            container.with_command("/bin/sh -c 'sleep infinity'")

            try:
                container.start()

                with subtests.test("/proc/sys/crypto/fips_enabled is 1"):
                    ecode, output = container.exec(["/bin/sh", "-c", "sysctl crypto.fips_enabled"])
                    assert ecode == 0, output.decode()
                    assert "crypto.fips_enabled = 1\n" == output.decode(), output.decode()

                # 0: enabled, 1: partial success, 2: not enabled
                with subtests.test("/fips-mode-setup --is-enabled reports 1"):
                    ecode, output = container.exec(["/bin/sh", "-c", "fips-mode-setup --is-enabled"])
                    assert ecode == 1, output.decode()

                with subtests.test("/fips-mode-setup --check reports partial success"):
                    ecode, output = container.exec(["/bin/sh", "-c", "fips-mode-setup --check"])
                    assert ecode == 1, output.decode()
                    assert "FIPS mode is enabled.\n" in output.decode(), output.decode()
                    assert "Inconsistent state detected.\n" in output.decode(), output.decode()

                with subtests.test("oc version command runs"):
                    ecode, output = container.exec(["/bin/sh", "-c", "oc version"])
                    assert ecode == 0, output.decode()
            finally:
                docker_utils.NotebookContainer(container).stop(timeout=0)

    def test_pip_install_cowsay_runs(self, image: str):
        """Checks that the Python virtualenv in the image is writable."""
        container = testcontainers.core.container.DockerContainer(image=image, user=23456, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")
        try:
            container.start()

            ecode, output = container.exec(["python3", "-m", "pip", "install", "cowsay"])
            logging.debug(output.decode())
            assert ecode == 0

            ecode, output = container.exec(["python3", "-m", "cowsay", "--text", "Hello world"])
            logging.debug(output.decode())
            assert ecode == 0
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)


def encode_python_function_execution_command_interpreter(python: str, function: Callable[..., Any], *args: list[Any]) -> \
        list[str]:
    """Returns a cli command that will run the given Python function encoded inline.
    All dependencies (imports, ...) must be part of function body."""
    code = textwrap.dedent(inspect.getsource(function))
    ccode = binascii.b2a_base64(code.encode())
    name = function.__name__
    parameters = ', '.join(repr(arg) for arg in args)
    program = textwrap.dedent(f"""
        import binascii;
        s=binascii.a2b_base64("{ccode.decode('ascii').strip()}");
        exec(s.decode());
        print({name}({parameters}));""")
    int_cmd = [python, "-c", program]
    return int_cmd
