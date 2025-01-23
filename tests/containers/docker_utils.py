from __future__ import annotations

import io
import logging
import os.path
import sys
import tarfile
import time
from typing import TYPE_CHECKING

import testcontainers.core.container

if TYPE_CHECKING:
    from docker.models.containers import Container


class NotebookContainer:
    @classmethod
    def wrap(cls, container: testcontainers.core.container.DockerContainer):
        return NotebookContainer(container)

    def __init__(self, container: testcontainers.core.container.DockerContainer) -> None:
        self.testcontainer = container

    def stop(self, timeout: int = 10):
        """Stop container with customizable timeout.

        DockerContainer.stop() has unchangeable 10s timeout between SIGSTOP and SIGKILL."""
        self.testcontainer.get_wrapped_container().stop(timeout=timeout)
        self.testcontainer.stop()

    def wait_for_exit(self) -> int:
        container = self.testcontainer.get_wrapped_container()
        container.reload()
        while container.status != "exited":
            time.sleep(0.2)
            container.reload()
        return container.attrs["State"]["ExitCode"]


def container_cp(container: Container, src: str, dst: str,
                 user: int | None = None, group: int | None = None) -> None:
    """
    Copies a directory into a container
    From https://stackoverflow.com/questions/46390309/how-to-copy-a-file-from-host-to-container-using-docker-py-docker-sdk
    """
    fh = io.BytesIO()
    tar = tarfile.open(fileobj=fh, mode="w:gz")

    tar_filter = None
    if user or group:
        def tar_filter(f: tarfile.TarInfo) -> tarfile.TarInfo:
            if user:
                f.uid = user
            if group:
                f.gid = group
            return f

    logging.debug(f"Adding {src=} to archive {dst=}")
    try:
        tar.add(src, arcname=os.path.basename(src), filter=tar_filter)
    finally:
        tar.close()

    fh.seek(0)
    container.put_archive(dst, fh)


def from_container_cp(container: Container, src: str, dst: str) -> None:
    fh = io.BytesIO()
    bits, stat = container.get_archive(src, encode_stream=True)
    for chunk in bits:
        fh.write(chunk)
    fh.seek(0)
    tar = tarfile.open(fileobj=fh, mode="r")
    try:
        tar.extractall(path=dst, filter=tarfile.data_filter)
    finally:
        tar.close()
        fh.close()


def container_exec(
        container: Container,
        cmd: str | list[str],
        stdout: bool = True,
        stderr: bool = True,
        stdin: bool = False,
        tty: bool = False,
        privileged: bool = False,
        user: str = "",
        detach: bool = False,
        stream: bool = False,
        socket: bool = False,
        environment: dict[str, str] | None = None,
        workdir: str | None = None,
) -> ContainerExec:
    """
    An enhanced version of #docker.Container.exec_run() which returns an object
    that can be properly inspected for the status of the executed commands.
    Usage example:
    result = tools.container_exec(container, cmd, stream=True, **kwargs)
    res = result.communicate(line_prefix=b'--> ')
    if res != 0:
        error('exit code {!r}'.format(res))
    From https://github.com/docker/docker-py/issues/1989
    """

    exec_id = container.client.api.exec_create(
        container.id,
        cmd,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        tty=tty,
        privileged=privileged,
        user=user,
        environment=environment,
        workdir=workdir,
    )["Id"]

    output = container.client.api.exec_start(exec_id, detach=detach, tty=tty, stream=stream, socket=socket)

    return ContainerExec(container.client, exec_id, output)


class ContainerExec:
    def __init__(self, client, id, output: list[int] | list[str]):
        self.client = client
        self.id = id
        self.output = output

    def inspect(self):
        return self.client.api.exec_inspect(self.id)

    def poll(self):
        return self.inspect()["ExitCode"]

    def communicate(self, line_prefix=b""):
        for data in self.output:
            if not data:
                continue
            offset = 0
            while offset < len(data):
                sys.stdout.buffer.write(line_prefix)
                nl = data.find(b"\n", offset)
                if nl >= 0:
                    slice = data[offset: nl + 1]
                    offset = nl + 1
                else:
                    slice = data[offset:]
                    offset += len(slice)
                sys.stdout.buffer.write(slice)
            sys.stdout.flush()
        while self.poll() is None:
            raise RuntimeError("Hm could that really happen?")
        return self.poll()
