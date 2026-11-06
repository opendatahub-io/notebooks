from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

from manifests.tools.notebook_metadata import (
    MANIFESTS_ODH_DIR,
    ROOT_DIR,
    NotebookMetadata,
    NotebookType,
    extract_metadata_from_path,
    get_source_of_truth_filepath,
)

_TEST_MANIFESTS_ODH_DIR = Path("notebooks/manifests/odh")  # for unit tests using relative paths

MAKE = shutil.which("gmake") or shutil.which("make")


class TestManifests:
    def test_jupyter_minimal_cuda_metadata_when_cuda_and_rocm_dockerfiles(self):
        """Minimal stack dir holds both Konflux CUDA and ROCm Dockerfiles; CUDA wins."""
        metadata = extract_metadata_from_path(ROOT_DIR / "jupyter/minimal/ubi9-python-3.12")
        assert metadata == NotebookMetadata(
            type=NotebookType.WORKBENCH,
            feature="jupyter",
            scope="minimal",
            os_flavor="ubi9",
            python_flavor="python-3.12",
            accelerator_flavor="cuda",
        )

    def test_jupyter_minimal_rocm_metadata_isolated_rocm_dockerfile(self):
        """Deterministic ROCm: only Dockerfile.konflux.rocm in a minimal layout path."""
        with tempfile.TemporaryDirectory() as tmp:
            minimal_dir = Path(tmp) / "jupyter" / "minimal" / "ubi9-python-3.12"
            minimal_dir.mkdir(parents=True)
            (minimal_dir / "Dockerfile.konflux.rocm").write_text("# test stub\n", encoding="utf-8")

            metadata = extract_metadata_from_path(minimal_dir)
            assert metadata == NotebookMetadata(
                type=NotebookType.WORKBENCH,
                feature="jupyter",
                scope="minimal",
                os_flavor="ubi9",
                python_flavor="python-3.12",
                accelerator_flavor="rocm",
            )

    def test_runtime_cuda_tensorflow_manifest(self):
        metadata = extract_metadata_from_path(ROOT_DIR / "runtimes/tensorflow/ubi9-python-3.12")
        assert metadata.type == NotebookType.RUNTIME
        path = get_source_of_truth_filepath(manifests_directory=_TEST_MANIFESTS_ODH_DIR, metadata=metadata)
        assert path == _TEST_MANIFESTS_ODH_DIR / "base" / "jupyter-tensorflow-notebook-imagestream.yaml"

    def test_codeserver(self):
        metadata = extract_metadata_from_path(Path("notebooks/codeserver/ubi9-python-3.12"))
        assert metadata == NotebookMetadata(
            type=NotebookType.WORKBENCH,
            feature="codeserver",
            scope="datascience",
            os_flavor="ubi9",
            python_flavor="python-3.12",
            accelerator_flavor=None,
        )

    def test_codeserver_path(self):
        metadata = extract_metadata_from_path(Path("notebooks/codeserver/ubi9-python-3.12"))
        path = get_source_of_truth_filepath(manifests_directory=_TEST_MANIFESTS_ODH_DIR, metadata=metadata)
        assert path == _TEST_MANIFESTS_ODH_DIR / "base" / "code-server-notebook-imagestream.yaml"

    def run_shell_function(
        self,
        shell_script_path: Path,
        shell_function_name: str,
        script_args: Iterable[str] = (),
        function_args: Iterable[str] = (),
        env: dict[str, str] | None = None,
    ) -> str:
        env = env or {}
        script_args_str = " ".join(shlex.quote(arg) for arg in script_args)
        function_args_str = " ".join(shlex.quote(arg) for arg in function_args)
        command = (
            f"set -- {script_args_str} && "
            f"source {shlex.quote(str(shell_script_path))} && "
            f"set -- && {shlex.quote(shell_function_name)} {function_args_str}"
        )
        shell_notebook_id = subprocess.run(
            ["bash", "-c", command],
            env=env,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        return shell_notebook_id.stdout.rstrip()

    @staticmethod
    def get_targets() -> list[tuple[str, Path]]:
        # TODO(jdanek): should systematize import paths to avoid this hack
        sys.path.insert(0, str(ROOT_DIR / "ci/cached-builds"))
        from ci.cached_builds import gen_gha_matrix_jobs  # ruff: ignore[import-outside-top-level]

        python_312 = gen_gha_matrix_jobs.extract_image_targets(ROOT_DIR, env={"RELEASE_PYTHON_VERSION": "3.12"})
        targets = python_312
        # TODO(jdanek): this is again duplicating knowledge, but, what can I do?
        expected_manifest_paths = {
            "jupyter-minimal-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-minimal-notebook-imagestream.yaml",
            "runtime-minimal-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-minimal-notebook-imagestream.yaml",
            # no -gpu-?
            "cuda-jupyter-minimal-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-minimal-gpu-notebook-imagestream.yaml",
            "rocm-jupyter-minimal-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-rocm-minimal-notebook-imagestream.yaml",
            "jupyter-datascience-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-datascience-notebook-imagestream.yaml",
            "jupyter-baseline-c9s-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-baseline-notebook-imagestream.yaml",
            "jupyter-baseline-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-baseline-notebook-imagestream.yaml",
            "runtime-baseline-c9s-python-3.12": MANIFESTS_ODH_DIR / "base" / "runtime-baseline-imagestream.yaml",
            "runtime-baseline-ubi9-python-3.12": MANIFESTS_ODH_DIR / "base" / "runtime-baseline-imagestream.yaml",
            "runtime-datascience-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-datascience-notebook-imagestream.yaml",
            "cuda-jupyter-pytorch-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-pytorch-notebook-imagestream.yaml",
            "runtime-cuda-pytorch-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-pytorch-notebook-imagestream.yaml",
            "cuda-jupyter-pytorch-llmcompressor-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-pytorch-notebook-imagestream.yaml",
            "runtime-cuda-pytorch-llmcompressor-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-pytorch-notebook-imagestream.yaml",
            "cuda-jupyter-tensorflow-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-tensorflow-notebook-imagestream.yaml",
            "runtime-cuda-tensorflow-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-tensorflow-notebook-imagestream.yaml",
            "jupyter-universal-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "jupyter-universal-notebook-imagestream.yaml",
            "codeserver-ubi9-python-3.12": MANIFESTS_ODH_DIR / "base" / "code-server-notebook-imagestream.yaml",
            "codeserver-baseline-c9s-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "code-server-baseline-notebook-imagestream.yaml",
            "codeserver-baseline-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "code-server-baseline-notebook-imagestream.yaml",
            "codeserver-minimal-ubi9-python-3.12": MANIFESTS_ODH_DIR
            / "base"
            / "code-server-minimal-notebook-imagestream.yaml",
        }
        rows: list[tuple[str, Path]] = []
        for target in targets:
            if "codeserver" in target and "baseline" not in target:
                continue
            try:
                expected_manifest_path = expected_manifest_paths[target]
            except KeyError as e:
                raise ValueError(f"Missing expected manifest path for target '{target}'") from e
            rows.append((target, expected_manifest_path))
        return rows

    @pytest.mark.parametrize("target,expected_manifest_path", get_targets())
    def test_compare_with_shell_implementation(self, target: str, expected_manifest_path: Path):
        shell_script_path = ROOT_DIR / "scripts/test_jupyter_with_papermill.sh"

        notebook_id = self.run_shell_function(
            shell_script_path,
            "_get_notebook_id",
            script_args=[target],
            env={"notebook_workload_name": target},
        )
        assert notebook_id

        source_of_truth_filepath = self.run_shell_function(
            shell_script_path,
            "_get_source_of_truth_filepath",
            script_args=[target],
            function_args=[notebook_id],
        )
        assert source_of_truth_filepath == str(expected_manifest_path)
