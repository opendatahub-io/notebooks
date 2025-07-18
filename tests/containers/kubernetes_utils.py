from __future__ import annotations

import contextlib
import functools
import logging
import socket
import subprocess
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any, Literal, Self

import kubernetes
import kubernetes.client.api.core_v1_api
import kubernetes.dynamic.exceptions
import kubernetes.stream.ws_client
import ocp_resources.deployment
import ocp_resources.namespace
import ocp_resources.persistent_volume_claim
import ocp_resources.pod
import ocp_resources.project_project_openshift_io
import ocp_resources.project_request
import ocp_resources.resource
import ocp_resources.service
import requests

from tests.containers import socket_proxy

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from socket import socket

    from kubernetes.dynamic import DynamicClient, ResourceField


class TestFrameConstants:
    GLOBAL_POLL_INTERVAL_MEDIUM = 10
    TIMEOUT_2MIN = 2 * 60
    TIMEOUT_5MIN = 5 * 60
    TIMEOUT_20MIN = 20 * 60

    # this includes potentially pulling the image, and cuda images are huge
    READINESS_TIMEOUT = TIMEOUT_5MIN


logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)


# https://github.com/RedHatQE/openshift-python-wrapper/tree/main/examples


def get_client() -> kubernetes.dynamic.DynamicClient:
    try:
        # client = kubernetes.dynamic.DynamicClient(client=kubernetes.config.new_client_from_config())
        # probably same as above
        client = ocp_resources.resource.get_client()
        return client
    except kubernetes.config.ConfigException as e:
        # probably bad config
        logging.error(e)
    except kubernetes.dynamic.exceptions.UnauthorizedError as e:
        # wrong or expired credentials
        logging.error(e)
    except kubernetes.client.ApiException as e:
        # unexpected, we catch unauthorized above
        logging.error(e)
    except Exception as e:
        # unexpected error, assert here
        logging.error(e)

    raise RuntimeError("Failed to instantiate client")


def get_username(client: kubernetes.dynamic.DynamicClient) -> str:
    # can't just access
    # > client.configuration.username
    # because we normally auth using tokens, not username and password

    # this is what kubectl does (see kubectl -v8 auth whoami)
    self_subject_review_resource: kubernetes.dynamic.Resource = client.resources.get(
        api_version="authentication.k8s.io/v1", kind="SelfSubjectReview"
    )
    self_subject_review: kubernetes.dynamic.ResourceInstance = client.create(self_subject_review_resource)
    username: str = self_subject_review.status.userInfo.username
    return username


class TestKubernetesUtils:
    def test_get_username(self):
        client = get_client()
        username = get_username(client)
        assert username is not None and len(username) > 0


class TestFrame[S]:
    __test__ = False

    def __init__(self):
        self.stack: list[tuple[S, Callable[[S], None] | None]] = []

    def defer_resource[T: ocp_resources.resource.Resource](
        self, resource: T, wait=False, destructor: Callable[[T], None] | None = None
    ) -> T:
        result = resource.deploy(wait=wait)
        self.defer(resource, destructor)
        return result

    def defer[T](self, obj: T, destructor: Callable[[T], None] | None = None) -> T:
        self.stack.append((obj, destructor))
        return obj

    def destroy(self, wait=False):
        while self.stack:
            resource, destructor = self.stack.pop()
            if destructor is not None:
                destructor(resource)
            elif isinstance(resource, ocp_resources.resource.Resource):
                resource.clean_up(wait=wait)

    def __enter__(self) -> TestFrame[S]:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.destroy(wait=True)


class ImageDeployment:
    def __init__(self, client: kubernetes.dynamic.DynamicClient, image: str):
        self.client = client
        self.image = image
        self.pod = None
        self.port = None
        self.tf = TestFrame()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tf.destroy(wait=True)

    def deploy(
        self,
        container_name: str,
        accelerator: Literal["amd.com/gpu", "nvidia.com/gpu"] | None = None,
        is_runtime_image: bool = False,
        timeout: float = TestFrameConstants.READINESS_TIMEOUT,
    ) -> kubernetes.client.models.v1_pod.V1Pod:
        LOGGER.debug(f"Deploying {self.image}")
        # custom namespace is necessary, because we cannot assign a SCC to pods created in one of the default namespaces:
        #  default, kube-system, kube-public, openshift-node, openshift-infra, openshift.
        # https://docs.openshift.com/container-platform/4.17/authentication/managing-security-context-constraints.html#role-based-access-to-ssc_configuring-internal-oauth

        # TODO(jdanek): sort out how we want to work with privileged/unprivileged client
        #  take inspiration from odh-tests
        ns = create_namespace(privileged_client=True, name=f"test-ns-{container_name}")
        self.tf.defer_resource(ns)

        pvc = ocp_resources.persistent_volume_claim.PersistentVolumeClaim(
            name=container_name,
            namespace=ns.name,
            accessmodes=ocp_resources.persistent_volume_claim.PersistentVolumeClaim.AccessMode.RWO,
            volume_mode=ocp_resources.persistent_volume_claim.PersistentVolumeClaim.VolumeMode.FILE,
            size="1Gi",
        )
        self.tf.defer_resource(pvc, wait=True)
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
                        # Keep in mind that `default` is a privileged namespace and this annotation has no effect there.
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
                    },
                },
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "image": self.image,
                            # "command": ["/bin/sh", "-c", "while true; do date; sleep 5; done;"],
                            **(
                                {
                                    "command": ["/bin/sh"],
                                    "args": ["-c", "sleep infinity"],
                                }
                                if is_runtime_image
                                else {}
                            ),
                            "ports": [
                                {
                                    "containerPort": 8888,
                                    "name": "notebook-port",
                                    "protocol": "TCP",
                                }
                            ],
                            **(
                                {
                                    "resources": {
                                        "limits": {
                                            accelerator: "1",
                                        },
                                        "requests": {
                                            accelerator: "1",
                                        },
                                    }
                                }
                                if accelerator
                                else {}
                            ),
                            # rstudio will not start without its volume mount and it does not log the error for it
                            # See the testcontainers implementation of this (the tty=True part)
                            "volumeMounts": [{"mountPath": "/opt/app-root/src", "name": "my-workbench"}],
                        },
                    ],
                    "volumes": [
                        {
                            "name": "my-workbench",
                            "persistentVolumeClaim": {
                                "claimName": container_name,
                            },
                        }
                    ],
                },
            },
        )
        self.tf.defer_resource(deployment)
        LOGGER.debug("Waiting for pods to become ready...")
        PodUtils.wait_for_pods_ready(
            self.client,
            namespace_name=ns.name,
            label_selector=f"app={container_name}",
            expect_pods_count=1,
            timeout=timeout,
        )

        core_v1_api = kubernetes.client.api.core_v1_api.CoreV1Api(api_client=self.client.client)
        pod_name: kubernetes.client.models.v1_pod_list.V1PodList = core_v1_api.list_namespaced_pod(
            namespace=ns.name, label_selector=f"app={container_name}"
        )
        assert len(pod_name.items) == 1
        self.pod: kubernetes.client.models.v1_pod.V1Pod = pod_name.items[0]

        if not is_runtime_image:
            p = socket_proxy.SocketProxy(lambda: exposing_contextmanager(core_v1_api, self.pod), "localhost", 0)
            t = threading.Thread(target=p.listen_and_serve_until_canceled)
            t.start()
            self.tf.defer(t, lambda thread: thread.join())
            self.tf.defer(p.cancellation_token, lambda token: token.cancel())

            self.port = p.get_actual_port()
            LOGGER.debug(f"Listening on port {self.port}")
            Wait.until(
                "Connecting to pod succeeds",
                1,
                30,
                lambda: requests.get(f"http://localhost:{self.port}").status_code == 200,
            )
            LOGGER.debug("Done setting up portforward")

        return self.pod

    # https://github.com/kubernetes-client/python/blob/master/examples/pod_exec.py
    def exec(self, command: str) -> subprocess.CompletedProcess:
        if not self.pod or not self.pod.metadata or not self.pod.metadata.name or not self.pod.metadata.namespace:
            raise RuntimeError("Pod information is not available for exec operation.")
        LOGGER.debug(f"Executing command {command}")
        core_v1_api = kubernetes.client.api.core_v1_api.CoreV1Api(api_client=self.client.client)

        # Uses kubernetes.stream.stream to handle WebSocket upgrade.
        # E   HTTP response body: {"kind":"Status","apiVersion":"v1","metadata":{},"status":"Failure","message":"Upgrade request required","reason":"BadRequest","code":400}
        try:
            resp: kubernetes.stream.ws_client.WSClient = kubernetes.stream.stream(
                core_v1_api.connect_get_namespaced_pod_exec,
                self.pod.metadata.name,
                self.pod.metadata.namespace,
                command=["/bin/sh", "-c", command],
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                # _preload_content=False is important for streaming
                _preload_content=False,
            )
        except Exception as e:
            LOGGER.error(f"Error during pod exec: {e}")
            LOGGER.error(traceback.format_exc())
            raise
        stdout = []
        stderr = []
        while resp.is_open():
            resp.update(timeout=1)
            if resp.peek_stdout():
                stdout.append(resp.read_stdout())
            if resp.peek_stderr():
                stderr.append(resp.read_stderr())
        returncode = resp.returncode
        resp.close()

        return subprocess.CompletedProcess(
            args=command, returncode=returncode, stdout="\n".join(stdout), stderr="\n".join(stderr)
        )


class PodUtils:
    # consider using timeout_sampler
    @staticmethod
    def wait_for_pods_ready(
        client: DynamicClient,
        namespace_name: str,
        label_selector: str,
        expect_pods_count: int,
        timeout: float = TestFrameConstants.READINESS_TIMEOUT,
    ) -> None:
        """Wait for all pods in namespace to be ready"""

        # it's a dynamic client with the `resource` parameter already filled in
        class ResourceType(kubernetes.dynamic.Resource, kubernetes.dynamic.DynamicClient):
            pass

        resource: ResourceType = client.resources.get(
            kind=ocp_resources.pod.Pod.kind,
            api_version=ocp_resources.pod.Pod.api_version,
        )

        def ready() -> bool:
            pods = resource.get(namespace=namespace_name, label_selector=label_selector).items
            if not pods and expect_pods_count == 0:
                logging.debug("All expected Pods %s in Namespace %s are ready", label_selector, namespace_name)
                return True
            if not pods:
                logging.debug("Pods matching %s/%s are not ready", namespace_name, label_selector)
                return False
            if len(pods) != expect_pods_count:
                logging.debug("Expected Pods %s/%s are not ready", namespace_name, label_selector)
                return False
            pod: ResourceField
            for pod in pods:
                if not Readiness.is_pod_ready(pod) and not Readiness.is_pod_succeeded(pod):
                    if not pod.status.containerStatuses:
                        pod_status = pod.status
                    else:
                        pod_status = {cs.name: cs.state for cs in pod.status.containerStatuses}

                    logging.debug("Pod is not ready: %s/%s (%s)", namespace_name, pod.metadata.name, pod_status)
                    return False
                else:
                    # check all containers in pods are ready
                    for cs in pod.status.containerStatuses:
                        if not (cs.ready or cs.state.get("terminated", {}).get("reason", "") == "Completed"):
                            logging.debug(
                                f"Container {cs.getName()} of Pod {namespace_name}/{pod.metadata.name} not ready ({cs.state=})"
                            )
                            return False
            logging.info("Pods matching %s/%s are ready", namespace_name, label_selector)
            return True

        Wait.until(
            description=f"readiness of all Pods matching {label_selector} in Namespace {namespace_name}",
            poll_interval=TestFrameConstants.GLOBAL_POLL_INTERVAL_MEDIUM,
            timeout=timeout,
            ready=ready,
        )


class Wait:
    @staticmethod
    def until(
        description: str,
        poll_interval: float,
        timeout: float,
        ready: Callable[[], bool],
        on_timeout: Callable[[], None] | None = None,
    ) -> None:
        """For every poll (happening once each {@code pollIntervalMs}) checks if supplier {@code ready} is true.

        If yes, the wait is closed. Otherwise, waits another {@code pollIntervalMs} and tries again.
        Once the wait timeout (specified by {@code timeoutMs} is reached and supplier wasn't true until that time,
        runs the {@code onTimeout} (f.e. print of logs, showing the actual value that was checked inside {@code ready}),
        and finally throws {@link WaitError}.
        @param description    information about on what we are waiting
        @param pollIntervalMs poll interval in milliseconds
        @param timeoutMs      timeout specified in milliseconds
        @param ready          {@link BooleanSupplier} containing code, which should be executed each poll,
                               verifying readiness of the particular thing
        @param onTimeout      {@link Runnable} executed once timeout is reached and
                               before the {@link WaitError} is thrown."""
        logging.info("Waiting for: %s", description)
        deadline = time.monotonic() + timeout

        exception_message: str | None = None
        previous_exception_message: str | None = None

        # in case we are polling every 1s, we want to print exception after x tries, not on the first try
        # for minutes poll interval will 2 be enough
        exception_appearance_count: int = 2 if (poll_interval // 60) > 0 else max(int(timeout // poll_interval // 4), 2)
        exception_count: int = 0
        new_exception_appearance: int = 0

        stack_trace_error: str | None = None

        while True:
            try:
                result: bool = ready()
            except KeyboardInterrupt:
                raise  # quick exit if the user gets tired of waiting
            except SyntaxError:  # this actually won't happen, but it's good to keep in mind
                raise  # quick exit in cases developer obviously screwed up
            except Exception as e:
                exception_message = str(e)

                exception_count += 1
                new_exception_appearance += 1
                if (
                    exception_count == exception_appearance_count
                    and exception_message is not None
                    and exception_message == previous_exception_message
                ):
                    logging.info(f"While waiting for: {description} exception occurred: {exception_message}")
                    # log the stacktrace
                    stack_trace_error = traceback.format_exc()
                elif (
                    exception_message is not None
                    and exception_message != previous_exception_message
                    and new_exception_appearance == 2
                ):
                    previous_exception_message = exception_message

                result = False

            time_left: float = deadline - time.monotonic()
            if result:
                return
            if time_left <= 0:
                if exception_count > 1:
                    logging.error("Exception waiting for: %s, %s", description, exception_message)

                    if stack_trace_error is not None:
                        # printing handled stacktrace
                        logging.error(stack_trace_error)
                if on_timeout is not None:
                    on_timeout()
                wait_exception: WaitError = WaitError(f"Timeout after {timeout} s waiting for {description}")
                logging.error(wait_exception)
                raise wait_exception

            sleep_time: float = min(poll_interval, time_left)
            time.sleep(sleep_time)


class WaitError(Exception):
    pass


class Readiness:
    @staticmethod
    def is_pod_ready(pod: ResourceField) -> bool:
        Utils.check_not_none(value=pod, message="Pod can't be null.")

        condition = ocp_resources.pod.Pod.Condition.READY
        status = ocp_resources.pod.Pod.Condition.Status.TRUE
        for cond in pod.get("status", {}).get("conditions", []):
            if cond["type"] == condition and cond["status"].casefold() == status.casefold():
                return True
        return False

    @staticmethod
    def is_pod_succeeded(pod: ResourceField) -> bool:
        Utils.check_not_none(value=pod, message="Pod can't be null.")
        return pod.status is not None and "Succeeded" == pod.status.phase


class Utils:
    @staticmethod
    def check_not_none(value: Any, message: str) -> None:
        if value is None:
            raise ValueError(message)


@contextlib.contextmanager
def exposing_contextmanager(
    core_v1_api: kubernetes.client.CoreV1Api, pod: kubernetes.client.models.V1Pod
) -> Generator[socket, None, None]:
    # If we e.g., specify the wrong port, the pf = portforward() call succeeds,
    # but pf.connected will later flip to False
    # we need to check that _everything_ works before moving on
    pf = None
    s = None
    while not pf or not pf.connected or not s:
        pf: kubernetes.stream.ws_client.PortForward = kubernetes.stream.portforward(
            api_method=core_v1_api.connect_get_namespaced_pod_portforward,
            name=pod.metadata.name,
            namespace=pod.metadata.namespace,
            ports=",".join(str(p) for p in [8888]),
        )
        s: kubernetes.stream.ws_client.PortForward._Port._Socket | socket.socket | None = pf.socket(8888)
    assert s, "Failed to establish connection"

    try:
        yield s
    finally:
        s.close()
        pf.close()


@functools.wraps(ocp_resources.namespace.Namespace.__init__)
def create_namespace(
    privileged_client: bool = False, *args, **kwargs
) -> ocp_resources.project_project_openshift_io.Project:
    if not privileged_client:
        with ocp_resources.project_request.ProjectRequest(*args, **kwargs):
            project = ocp_resources.project_project_openshift_io.Project(*args, **kwargs)
            project.wait_for_status(status=project.Status.ACTIVE, timeout=TestFrameConstants.TIMEOUT_2MIN)
            return project
    else:
        with ocp_resources.namespace.Namespace(*args, **kwargs) as ns:
            ns.wait_for_status(
                status=ocp_resources.namespace.Namespace.Status.ACTIVE, timeout=TestFrameConstants.TIMEOUT_2MIN
            )
            return ns


__all__ = [
    "ImageDeployment",
    "PodUtils",
    "TestFrame",
    "TestFrameConstants",
    "create_namespace",
    "exposing_contextmanager",
    "get_client",
    "get_username",
]
