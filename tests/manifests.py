# Based on the shell script's variable names for clarity in logic translation.
from __future__ import annotations

import dataclasses
import enum
import shlex
import shutil
import subprocess
import sys
import typing
from pathlib import Path

import pytest

if typing.TYPE_CHECKING:
    from collections.abc import Generator, Iterable

ROOT_DIR = Path(__file__).parent.parent

JUPYTER_MINIMAL_NOTEBOOK_ID = "minimal"
JUPYTER_DATASCIENCE_NOTEBOOK_ID = "datascience"
JUPYTER_TRUSTYAI_NOTEBOOK_ID = "trustyai"
JUPYTER_PYTORCH_NOTEBOOK_ID = "pytorch"
JUPYTER_TENSORFLOW_NOTEBOOK_ID = "tensorflow"

CODESERVER_NOTEBOOK_ID = "codeserver"

RSTUDIO_NOTEBOOK_ID = "rstudio"

MAKE = shutil.which("gmake") or shutil.which("make")


@enum.unique
class NotebookType(enum.Enum):
    """Enum for the different notebook types."""

    RUNTIME = "runtime"
    WORKBENCH = "workbench"


@dataclasses.dataclass(frozen=True)
class NotebookMetadata:
    """Stores metadata parsed from a notebook's directory path."""

    type: NotebookType
    feature: str

    """Name of the notebook identifier (e.g., 'minimal', 'pytorch')."""
    scope: str

    """The operating system flavor (e.g., 'ubi9')"""
    os_flavor: str

    """The python version string (e.g., 'python-3.12')"""
    python_flavor: str

    """The accelerator flavor (e.g., 'cuda', 'cpu', or None)"""
    accelerator_flavor: str | None


def extract_metadata_from_path(directory: Path) -> NotebookMetadata:
    """
    Parses a notebook's directory path to extract metadata needed to find its manifest.
    This logic is derived from the test_jupyter_with_papermill.sh script.

    Args:
        directory: The directory containing the notebook's pyproject.toml.
                   (e.g., .../jupyter/rocm/tensorflow/ubi9-python-3.12)

    Returns:
        A dataclass containing the parsed notebook metadata.

    Raises:
        ValueError: If the path format is unexpected and metadata cannot be extracted.
    """
    # 1. Parse OS and Python flavor from the directory name
    os_python_part = directory.name  # e.g., 'ubi9-python-3.12'
    try:
        os_flavor, python_version_str = os_python_part.split("-python-")
        python_flavor = f"python-{python_version_str}"
    except ValueError as e:
        raise ValueError(f"Directory name '{os_python_part}' does not match 'os-python-version' format.") from e

    # 2. Find the notebook's characteristic path components
    path_parts = directory.parts
    # Find the root component ('jupyter', 'runtimes', etc.) to anchor the search
    for root_candidate in ("jupyter", "codeserver", "rstudio", "runtimes"):
        try:
            start_index = path_parts.index(root_candidate)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Cannot determine notebook root in path: {directory}") from None

    # The parts between the root and the OS/python dir define the notebook flavor
    # e.g., ('minimal',), ('rocm', 'tensorflow',), ('pytorch',)
    notebook_identity_parts = path_parts[start_index + 1 : -1]

    # Determine scope (e.g., 'minimal', 'tensorflow')
    # The shell script uses the last part of the path-like notebook_id.
    try:
        scope = notebook_identity_parts[-1]
    except IndexError:
        # rstudio and codeserver don't have scope
        scope = ""
    if "-" in scope:
        assert path_parts[start_index] == "runtimes", "this naming pattern only appears in rocm runtime images"
        scope = scope.split("-", 1)[-1]

    # Determine accelerator flavor
    accelerator_flavor = None
    if "rocm" in notebook_identity_parts:
        accelerator_flavor = "rocm"
    elif "cuda" in notebook_identity_parts:
        accelerator_flavor = "cuda"
    # The shell script has an implicit rule for pytorch being cuda. We can
    # replicate this by checking for a specific Dockerfile.
    elif (directory / "Dockerfile.cuda").exists():
        accelerator_flavor = "cuda"
    elif (directory / "Dockerfile.rocm").exists():
        accelerator_flavor = "rocm"

    return NotebookMetadata(
        type=NotebookType.RUNTIME if "runtimes" == path_parts[start_index] else NotebookType.WORKBENCH,
        feature="runtime" if path_parts[start_index] == "runtimes" else path_parts[start_index],
        scope="datascience" if path_parts[start_index] == "codeserver" else scope,
        os_flavor=os_flavor,
        python_flavor=python_flavor,
        accelerator_flavor=accelerator_flavor,
    )


def get_source_of_truth_filepath(
    root_repo_directory: Path,
    metadata: NotebookMetadata,
) -> Path:
    """
    Computes the absolute path of the imagestream manifest for the notebook under test.
    This is a Python conversion of the shell function `_get_source_of_truth_filepath`.

    Returns:
        The absolute path to the imagestream manifest file.

    Raises:
        ValueError: If the logic cannot determine the filename for the given inputs.
    """
    notebook_id = metadata.feature
    scope = metadata.scope.replace("+", "-")  # pytorch+llmcompressor
    accelerator_flavor = metadata.accelerator_flavor

    if "llmcompressor" in scope:
        file_suffix = "imagestream.yaml"
    else:
        file_suffix = "notebook-imagestream.yaml"

    manifest_directory = root_repo_directory / "manifests"
    imagestream_directory = manifest_directory / "base"

    filename = ""

    if "runtime" == notebook_id:
        accelerator_prefix = f"{accelerator_flavor}-" if accelerator_flavor else ""
        filename = f"jupyter-{accelerator_prefix}{scope}-{file_suffix}"
        if accelerator_flavor == "cuda":
            filename = f"jupyter-{scope}-{file_suffix}"

    elif "jupyter" in notebook_id:
        if scope == JUPYTER_MINIMAL_NOTEBOOK_ID:
            # Logic for minimal notebook
            accelerator_prefix = f"{accelerator_flavor}-" if accelerator_flavor else ""
            filename = f"jupyter-{accelerator_prefix}{scope}-{file_suffix}"
            if accelerator_flavor == "cuda":
                filename = f"jupyter-{scope}-gpu-{file_suffix}"

        elif scope in (JUPYTER_DATASCIENCE_NOTEBOOK_ID, JUPYTER_TRUSTYAI_NOTEBOOK_ID):
            # Logic for datascience and trustyai
            filename = f"jupyter-{scope}-{file_suffix}"

        elif JUPYTER_PYTORCH_NOTEBOOK_ID in scope or JUPYTER_TENSORFLOW_NOTEBOOK_ID in scope:
            # Logic for pytorch and tensorflow
            accelerator_prefix = f"{accelerator_flavor}-" if accelerator_flavor else ""
            filename = f"jupyter-{accelerator_prefix}{scope}-{file_suffix}"
            if accelerator_flavor == "cuda":
                # This override is intentionally different from the 'minimal' one, as per the script
                filename = f"jupyter-{scope}-{file_suffix}"

    elif CODESERVER_NOTEBOOK_ID in notebook_id:
        filename = f"code-server-{file_suffix}"

    elif RSTUDIO_NOTEBOOK_ID in notebook_id:
        imagestream_filename = f"rstudio-gpu-{file_suffix}"
        buildconfig_filename = "cuda-rstudio-buildconfig.yaml"
        _ = imagestream_filename
        filename = buildconfig_filename

    if not filename:
        raise ValueError(f"Unable to determine imagestream filename for '{metadata=}'")

    filepath = imagestream_directory / filename

    return filepath


class TestManifests:
    def test_rstudio_path(self):
        metadata = extract_metadata_from_path(Path("notebooks/rstudio/rhel9-python-3.11"))
        assert metadata == NotebookMetadata(
            type=NotebookType.WORKBENCH,
            feature="rstudio",
            scope="",
            os_flavor="rhel9",
            python_flavor="python-3.11",
            accelerator_flavor=None,
        )

    def test_rstudio_truth_manifest(self):
        metadata = extract_metadata_from_path(Path("notebooks/rstudio/rhel9-python-3.11"))
        path = get_source_of_truth_filepath(root_repo_directory=Path("notebooks"), metadata=metadata)
        assert path == Path("notebooks/manifests/base/cuda-rstudio-buildconfig.yaml")

    def test_jupyter_path(self):
        metadata = extract_metadata_from_path(Path("notebooks/jupyter/rocm/tensorflow/ubi9-python-3.12"))
        assert metadata == NotebookMetadata(
            type=NotebookType.WORKBENCH,
            feature="jupyter",
            scope="tensorflow",
            os_flavor="ubi9",
            python_flavor="python-3.12",
            accelerator_flavor="rocm",
        )

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
        path = get_source_of_truth_filepath(root_repo_directory=Path("notebooks"), metadata=metadata)
        assert path == Path("notebooks/manifests/base/code-server-notebook-imagestream.yaml")

    def test_runtime_pytorch_path(self):
        metadata = extract_metadata_from_path(
            Path("/Users/jdanek/IdeaProjects/notebooks/runtimes/rocm-tensorflow/ubi9-python-3.12")
        )
        assert metadata == NotebookMetadata(
            type=NotebookType.RUNTIME,
            feature="runtime",
            scope="tensorflow",
            os_flavor="ubi9",
            python_flavor="python-3.12",
            accelerator_flavor="rocm",
        )

    def test_jupyter_pytorch_path(self):
        """We need to get path to the Jupyter imagestream, not to runtime imagestream"""
        metadata = extract_metadata_from_path(
            Path("/Users/jdanek/IdeaProjects/notebooks/runtimes/rocm-tensorflow/ubi9-python-3.12")
        )
        path = get_source_of_truth_filepath(root_repo_directory=Path("notebooks"), metadata=metadata)
        assert path == Path("notebooks/manifests/base/jupyter-rocm-tensorflow-notebook-imagestream.yaml")

    def test_source_of_truth_jupyter_tensorflow_rocm(self):
        metadata = extract_metadata_from_path(Path("notebooks/jupyter/rocm/tensorflow/ubi9-python-3.12"))
        path = get_source_of_truth_filepath(root_repo_directory=Path("notebooks"), metadata=metadata)
        assert path == Path("notebooks/manifests/base/jupyter-rocm-tensorflow-notebook-imagestream.yaml")

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
        shell_notebook_id = subprocess.run(
            # set temporary positional parameters for the `source`ing
            f"""set -- {script_args_str} && source {shell_script_path} && set -- && {shell_function_name} {function_args_str}""",
            shell=True,
            executable="/bin/bash",
            env=env,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        return shell_notebook_id.stdout.rstrip()

    @staticmethod
    def get_targets() -> Generator[tuple[str, Path], None, None]:
        # TODO(jdanek): should systematize import paths to avoid this hack
        sys.path.insert(0, str(ROOT_DIR / "ci/cached-builds"))
        from ci.cached_builds import gen_gha_matrix_jobs  # noqa: PLC0415

        python_311 = gen_gha_matrix_jobs.extract_image_targets(ROOT_DIR, env={"RELEASE_PYTHON_VERSION": "3.11"})
        python_312 = gen_gha_matrix_jobs.extract_image_targets(ROOT_DIR, env={"RELEASE_PYTHON_VERSION": "3.12"})
        targets = python_311 + python_312
        # TODO(jdanek): this is again duplicating knowledge, but, what can I do?
        expected_manifest_paths = {
            "jupyter-minimal-ubi9-python-3.12": ROOT_DIR / "manifests/base/jupyter-minimal-notebook-imagestream.yaml",
            "runtime-minimal-ubi9-python-3.12": ROOT_DIR / "manifests/base/jupyter-minimal-notebook-imagestream.yaml",
            # no -gpu-?
            "cuda-jupyter-minimal-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-minimal-notebook-imagestream.yaml",
            "rocm-jupyter-minimal-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-minimal-notebook-imagestream.yaml",
            "jupyter-datascience-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-datascience-notebook-imagestream.yaml",
            "runtime-datascience-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-datascience-notebook-imagestream.yaml",
            "cuda-jupyter-pytorch-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-pytorch-notebook-imagestream.yaml",
            "runtime-cuda-pytorch-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-pytorch-notebook-imagestream.yaml",
            "rocm-jupyter-pytorch-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-pytorch-notebook-imagestream.yaml",
            "rocm-runtime-pytorch-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-pytorch-notebook-imagestream.yaml",
            "cuda-jupyter-pytorch-llmcompressor-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-pytorch-notebook-imagestream.yaml",
            "runtime-cuda-pytorch-llmcompressor-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-pytorch-notebook-imagestream.yaml",
            "cuda-jupyter-tensorflow-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-tensorflow-notebook-imagestream.yaml",
            "runtime-cuda-tensorflow-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-tensorflow-notebook-imagestream.yaml",
            "rocm-jupyter-tensorflow-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-tensorflow-notebook-imagestream.yaml",
            "rocm-runtime-tensorflow-ubi9-python-3.12": ROOT_DIR
            / "manifests/base/jupyter-tensorflow-notebook-imagestream.yaml",
            "jupyter-trustyai-ubi9-python-3.12": ROOT_DIR / "manifests/base/jupyter-trustyai-notebook-imagestream.yaml",
            "codeserver-ubi9-python-3.12": ROOT_DIR / "manifests/base/code-server-notebook-imagestream.yaml",
            "rstudio-ubi9-python-3.11": ROOT_DIR / "manifests/base/rstudio-buildconfig.yaml",
            "rstudio-c9s-python-3.11": ROOT_DIR / "manifests/base/rstudio-buildconfig.yaml",
            "cuda-rstudio-c9s-python-3.11": ROOT_DIR / "manifests/base/cuda-rstudio-buildconfig.yaml",
            "rstudio-rhel9-python-3.11": ROOT_DIR / "manifests/base/rstudio-buildconfig.yaml",
            "cuda-rstudio-rhel9-python-3.11": ROOT_DIR / "manifests/base/cuda-rstudio-buildconfig.yaml",
        }
        for target in targets:
            if "codeserver" in target:
                continue
            if "rstudio" in target:
                continue
            yield target, expected_manifest_paths[target]

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
