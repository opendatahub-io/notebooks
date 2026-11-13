# Based on the shell script's variable names for clarity in logic translation.
"""Map notebook image directory paths to ImageStream metadata and manifest filenames."""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

MANIFESTS_ODH_DIR = ROOT_DIR / "manifests" / "odh"
MANIFESTS_RHOAI_DIR = ROOT_DIR / "manifests" / "rhoai"

JUPYTER_MINIMAL_NOTEBOOK_ID = "minimal"
JUPYTER_BASELINE_NOTEBOOK_ID = "baseline"
JUPYTER_DATASCIENCE_NOTEBOOK_ID = "datascience"
JUPYTER_UNIVERSAL_NOTEBOOK_ID = "universal"
JUPYTER_PYTORCH_NOTEBOOK_ID = "pytorch"
JUPYTER_TENSORFLOW_NOTEBOOK_ID = "tensorflow"

CODESERVER_NOTEBOOK_ID = "codeserver"


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
                   (e.g., .../jupyter/minimal/ubi9-python-3.12)

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
    for root_candidate in ("codeserver-baseline", "codeserver-minimal", "jupyter", "codeserver", "runtimes"):
        try:
            start_index = path_parts.index(root_candidate)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Cannot determine notebook root in path: {directory}") from None

    # The parts between the root and the OS/python dir define the notebook flavor
    # e.g., ('minimal',), ('baseline',), ('rocm', 'tensorflow',), ('pytorch',)
    notebook_identity_parts = path_parts[start_index + 1 : -1]

    if path_parts[start_index] == "codeserver-baseline":
        scope = JUPYTER_BASELINE_NOTEBOOK_ID
    else:
        # Determine scope (e.g., 'minimal', 'tensorflow')
        # The shell script uses the last part of the path-like notebook_id.
        try:
            scope = notebook_identity_parts[-1]
        except IndexError:
            # codeserver doesn't have scope
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
    # jupyter/pytorch has no "cuda" in the path; papermill treats jupyter-pytorch-* as cuda
    # via name matching (_get_accelerator_flavor in test_jupyter_with_papermill.sh).
    # When inferring from a directory path, detect cuda/rocm from Dockerfile.konflux.* variants.
    elif (directory / "Dockerfile.konflux.cuda").exists():
        accelerator_flavor = "cuda"
    elif (directory / "Dockerfile.konflux.rocm").exists():
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
    manifests_directory: Path,
    metadata: NotebookMetadata,
) -> Path:
    """
    Computes the absolute path of the imagestream manifest for the notebook under test.
    This is a Python conversion of the shell function `_get_source_of_truth_filepath`.

    Returns:
        The path to the imagestream manifest file, relative to manifests_directory.

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

    filename = ""

    if "runtime" == notebook_id:
        if scope == JUPYTER_BASELINE_NOTEBOOK_ID:
            filename = "runtime-baseline-imagestream.yaml"
        else:
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

        elif scope in (JUPYTER_DATASCIENCE_NOTEBOOK_ID, JUPYTER_UNIVERSAL_NOTEBOOK_ID):
            # Logic for datascience and universal
            filename = f"jupyter-{scope}-{file_suffix}"

        elif scope == JUPYTER_BASELINE_NOTEBOOK_ID:
            filename = f"jupyter-baseline-{file_suffix}"

        elif JUPYTER_PYTORCH_NOTEBOOK_ID in scope or JUPYTER_TENSORFLOW_NOTEBOOK_ID in scope:
            # Logic for pytorch and tensorflow
            accelerator_prefix = f"{accelerator_flavor}-" if accelerator_flavor else ""
            filename = f"jupyter-{accelerator_prefix}{scope}-{file_suffix}"
            if accelerator_flavor == "cuda":
                # This override is intentionally different from the 'minimal' one, as per the script
                filename = f"jupyter-{scope}-{file_suffix}"

    elif CODESERVER_NOTEBOOK_ID in notebook_id or notebook_id == "codeserver-baseline":
        if notebook_id == "codeserver-minimal":
            filename = f"code-server-minimal-{file_suffix}"
        elif notebook_id == "codeserver-baseline" or scope == JUPYTER_BASELINE_NOTEBOOK_ID:
            filename = f"code-server-baseline-{file_suffix}"
        else:
            filename = f"code-server-{file_suffix}"

    if not filename:
        raise ValueError(f"Unable to determine imagestream filename for '{metadata=}'")

    return manifests_directory / "base" / filename
