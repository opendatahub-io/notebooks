import os
import select
import subprocess
import sys
import threading
import unittest
from pathlib import Path

try:
    import pytest
except ImportError:

    class pytest:
        class _Mark:
            @classmethod
            def __getattr__(cls, item):
                return lambda x: x

        mark = _Mark()


import probe_check


@pytest.mark.buildonlytest
class TestStartup(unittest.TestCase):
    def setUp(self):
        self.project_name = "projectName"
        self.notebook_id = "notebookId"
        self.translated_username = "sometranslatedUsername"
        self.origin = "https://origin"
        self.root_dir = Path(__file__).parent

    def get_notebook_args_configuration(self) -> str:
        expected_args = " ".join(
            [
                "--ServerApp.port=8888",
                "--ServerApp.token=''",
                "--ServerApp.password=''",
                f"--ServerApp.base_url=/notebook/{self.project_name}/{self.notebook_id}",
                "--ServerApp.quit_button=False",
                f'--ServerApp.tornado_settings={{"user":"{self.translated_username}","hub_host":"{self.origin}","hub_prefix":"/projects/{self.project_name}"}}',
            ]
        )
        return expected_args

    def get_environment_variables(self) -> dict[str, str]:
        notebook_args = self.get_notebook_args_configuration()
        nb_prefix = f"/notebook/{self.project_name}/{self.notebook_id}"
        return {
            # (outdated?) https://github.com/opendatahub-io/odh-dashboard/blob/2.4.0-release/backend/src/utils/notebookUtils.ts#L284-L293
            # https://github.com/opendatahub-io/odh-dashboard/blob/1d5a9065c10acc4706b84b06c67f27f16cf6dee7/frontend/src/api/k8s/notebooks.ts#L157-L170
            "NOTEBOOK_ARGS": notebook_args,
            # NB_PREFIX is set by notebook-controller and codeserver scripting depends on it
            # https://github.com/opendatahub-io/kubeflow/blob/f924a96375988fe3801db883e99ce9ed1ab5939c/components/notebook-controller/controllers/notebook_controller.go#L417
            "NB_PREFIX": nb_prefix,
        }

    def test_codeserver_startup(self):
        env = self.get_environment_variables()
        command = ["/opt/app-root/bin/run-code-server.sh"]
        p = subprocess.Popen(
            command,
            # KFLUXSPRT-5139: https://redhat-internal.slack.com/archives/C04PZ7H0VA8/p1758128206734419
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, **env},
        )
        thr = threading.Thread(target=pump_stream, args=(p,), daemon=True)
        thr.start()

        try:
            ret = probe_check.main(self.project_name, self.notebook_id, "8888")
            self.assertEqual(ret, 0, "Probe check should return 0")
            self.assertEqual(p.poll(), None, "Code server process should still be running")
        finally:
            p.terminate()
            p.wait()

        thr.join()


def pump_stream(process: subprocess.Popen) -> None:
    """Copy everything from stream -> stdout."""
    # this may stop pumping even if there's something still buffered, so be it
    while process.returncode is None:
        rl, _, _ = select.select([process.stdout], [], [], 1)
        if rl:
            chunk = process.stdout.read1()
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    process.stdout.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
