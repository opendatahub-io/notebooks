"""Shared mapping from ImageStream manifest display names to Python package names.

Used by:
- ``tests/test_main.py`` — static pylock version alignment checks
- ``tests/containers/manifest_validation_test.py`` — SBOM/pip-list validation
- ``manifests/tools/update_imagestream_annotations_from_pylock.py`` — annotation refresh
"""

from __future__ import annotations

# Manifest display names that need explicit translation to pip/pylock names.
MANIFEST_TO_PIP: dict[str, str] = {
    "Elyra": "elyra-server",  # old (pre-odh-elyra) package name in 2023.x images
    "LLM-Compressor": "llmcompressor",
    "PyTorch": "torch",
    "ROCm-PyTorch": "torch",
    "Sklearn-onnx": "skl2onnx",
    "Nvidia-CUDA-CU12-Bundle": "nvidia-cuda-runtime-cu12",
    "MySQL Connector/Python": "mysql-connector-python",
    "ROCm-TensorFlow": "tensorflow-rocm",  # old name used in 2024.2 and earlier
    "TensorFlow-ROCm": "tensorflow-rocm",
}

# Manifest display names where ``.lower()`` gives the pip package name.
MANIFEST_LOWER_NAMES: frozenset[str] = frozenset(
    {
        "Accelerate",
        "Boto3",
        "Codeflare-SDK",
        "Datasets",
        "Feast",
        "JupyterLab",
        "Kafka-Python-ng",
        "Kfp",
        "Kubeflow-Training",
        "Matplotlib",
        "MLflow",
        "Numpy",
        "Odh-Elyra",
        "Pandas",
        "Psycopg",
        "PyMongo",
        "Pyodbc",
        "Scikit-learn",
        "Scipy",
        "TensorFlow",
        "Tensorboard",
        "Torch",
        "Transformers",
        "TrustyAI",
    }
)


def manifest_name_to_pip(name: str) -> str:
    """Convert a manifest display name to a pip/pylock package name."""
    translated = MANIFEST_TO_PIP.get(name)
    if translated is not None:
        return translated
    if name in MANIFEST_LOWER_NAMES:
        return name.lower()
    return name
