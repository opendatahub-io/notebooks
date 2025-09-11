# Based on the shell script's variable names for clarity in logic translation.
from __future__ import annotations

import dataclasses
import enum
import shutil
import unittest
from pathlib import Path

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

    elif JUPYTER_MINIMAL_NOTEBOOK_ID in scope:
        # Logic for minimal notebook
        accelerator_prefix = f"{accelerator_flavor}-" if accelerator_flavor else ""
        filename = f"jupyter-{accelerator_prefix}{scope}-{file_suffix}"
        if accelerator_flavor == "cuda":
            filename = f"jupyter-{scope}-gpu-{file_suffix}"

    elif JUPYTER_DATASCIENCE_NOTEBOOK_ID in scope or JUPYTER_TRUSTYAI_NOTEBOOK_ID in scope:
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


class SelfTests(unittest.TestCase):
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
