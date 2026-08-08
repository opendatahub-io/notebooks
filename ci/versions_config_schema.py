"""Generate JSON Schema for ``versions_config.yml`` (IDE validation).

Pydantic models here exist only to emit ``versions_config.schema.json`` for
``yaml-language-server``. Sync/rollout do not import this module; they keep
their own hand-rolled validation until a later migration.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema

_SEMVER_FRAGMENT = r"[0-9]+\.[0-9]+\.[0-9]+"
_STREAM_FRAGMENT = r"[0-9]+\.[0-9]+"
SEMVER_PATTERN = rf"^{_SEMVER_FRAGMENT}$"
PYTHON_VERSION_PATTERN = rf"^{_STREAM_FRAGMENT}$"
STREAM_VERSION_PATTERN = rf"^{_STREAM_FRAGMENT}$"
RHDS_OS_BASE_PATTERN = r"^el[0-9]+\.[0-9]+$"
FULL_VERSION_PLACEHOLDER = "<full_version>"
RHDS_FAST_CPU_VERSION_PATTERN = rf"^({_SEMVER_FRAGMENT}|{re.escape(FULL_VERSION_PLACEHOLDER)})$"
ACC_VERSION_PATTERN = rf"^({_STREAM_FRAGMENT}|{re.escape(FULL_VERSION_PLACEHOLDER)})$"

STRICT_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
)

SCHEMA_ID = "versions_config.schema.json"

SemVer = Annotated[str, StringConstraints(pattern=SEMVER_PATTERN)]
PythonVersion = Annotated[
    str,
    StringConstraints(pattern=PYTHON_VERSION_PATTERN),
    Field(
        title="Python version",
        description="Python interpreter major.minor version used for ODH CPU repository naming.",
        examples=["3.12"],
    ),
]
RhdsOsBase = Annotated[
    str,
    StringConstraints(pattern=RHDS_OS_BASE_PATTERN),
    Field(
        title="RHDS OS base",
        description='RHDS CUDA/ROCm repository OS suffix, for example "el9.6".',
        examples=["el9.6"],
    ),
]
RhdsFastCpuVersion = Annotated[
    str,
    StringConstraints(pattern=RHDS_FAST_CPU_VERSION_PATTERN),
    Field(
        title="RHDS CPU version",
        description=f'RHDS fast CPU release version, or "{FULL_VERSION_PLACEHOLDER}" to follow release.full_version.',
        examples=[FULL_VERSION_PLACEHOLDER, "3.5.0"],
    ),
]
AccVersion = Annotated[
    str,
    StringConstraints(pattern=ACC_VERSION_PATTERN),
    Field(
        title="Accelerator version",
        description=(
            "Accelerator stream (major.minor) shared by RHDS and ODH for this flavor, "
            f'or "{FULL_VERSION_PLACEHOLDER}". Nested acc_version under rhds/odh is not allowed.'
        ),
        examples=["13.0", "7.14"],
    ),
]
AIPCC_WHEEL_INDEX_STREAM_PATTERN = r"^[0-9]+\.[0-9]+(-EA[0-9]+)?$"
AipccWheelIndexStream = Annotated[
    str,
    StringConstraints(pattern=AIPCC_WHEEL_INDEX_STREAM_PATTERN),
    Field(
        title="AIPCC wheel index stream",
        description=(
            "AIPCC public-rhai rhoai path segment for base-images INDEX_URL "
            '(for example "3.5-EA2" or "3.5"). Independent of release.full_version.'
        ),
        examples=["3.5-EA2", "3.6-EA1", "3.5"],
    ),
]
OdhOrigin = Literal["in-house", "midstream"]
SchemaVersion = Literal[1]


class StrictModel(BaseModel):
    """Strict structural shapes for operator-edited YAML (feeds JSON Schema)."""

    model_config = STRICT_CONFIG


class AipccWheelIndex(StrictModel):
    """AIPCC wheel index stream baked into ODH base-images INDEX_URL build-args."""

    stream: AipccWheelIndexStream
    use_test: bool = Field(
        title="Use test index",
        description="When true, use *-ubi9-test simple indexes; when false, use prod *-ubi9 indexes.",
    )


class Release(StrictModel):
    """Release metadata shared across RHDS and ODH base-image resolution."""

    full_version: SemVer = Field(
        title="Full version",
        description="Product release in semantic version form; drives RHDS selection and Makefile RELEASE.",
        examples=["3.5.0"],
    )
    rhds_os_base: RhdsOsBase
    python_version: PythonVersion
    aipcc_wheel_index: AipccWheelIndex = Field(
        title="AIPCC wheel index",
        description=(
            "Operator input for base-images/build-args/*.conf INDEX_URL. Synced by make sync-build-args-from-versions."
        ),
    )


class RhdsFastCpuPolicy(StrictModel):
    """RHDS CPU policy for the progressing (fast) channel."""

    channel: Literal["fast"] = Field(title="Channel", description='Must be "fast" for this policy shape.')
    version: RhdsFastCpuVersion


class RhdsStableCpuPolicy(StrictModel):
    """RHDS CPU policy for the stable channel (version is derived from release.full_version)."""

    channel: Literal["stable"] = Field(title="Channel", description='Must be "stable" for this policy shape.')


RhdsCpuPolicy = Annotated[
    RhdsFastCpuPolicy | RhdsStableCpuPolicy,
    Field(discriminator="channel", title="RHDS CPU policy"),
]


class OdhCpuPolicy(StrictModel):
    """ODH CPU base-image policy."""

    origin: OdhOrigin = Field(
        title="Origin",
        description='ODH image origin: "in-house" or "midstream".',
    )
    version: Literal["latest"] = Field(
        title="Version",
        description="CPU ODH targets must stay on the rolling latest tag.",
    )


class CpuArtifact(StrictModel):
    """Shared CPU base-image policy (not per image-name)."""

    rhds: RhdsCpuPolicy
    odh: OdhCpuPolicy


class RhdsFastGpuPolicy(StrictModel):
    """RHDS GPU policy for the progressing (fast) channel. Stream comes from flavor-level acc_version."""

    channel: Literal["fast"] = Field(title="Channel", description='Must be "fast" for this policy shape.')


class RhdsStableGpuPolicy(StrictModel):
    """RHDS GPU policy for the stable channel. Stream matching uses flavor-level acc_version."""

    channel: Literal["stable"] = Field(title="Channel", description='Must be "stable" for this policy shape.')


RhdsGpuPolicy = Annotated[
    RhdsFastGpuPolicy | RhdsStableGpuPolicy,
    Field(discriminator="channel", title="RHDS GPU policy"),
]


class OdhGpuPolicy(StrictModel):
    """ODH GPU base-image policy. Stream comes from flavor-level acc_version."""

    origin: OdhOrigin = Field(
        title="Origin",
        description='ODH image origin: "in-house" or "midstream".',
    )


class GpuFlavor(StrictModel):
    """Shared GPU flavor policy block."""

    acc_version: AccVersion
    rhds: RhdsGpuPolicy
    odh: OdhGpuPolicy


type CudaFlavors = dict[str, GpuFlavor]
"""CUDA flavor policies. Keys are image/flavor IDs (e.g. minimal, pytorch-llmcompressor)."""

type RocmFlavors = dict[str, GpuFlavor]
"""ROCm flavor policies. Keys are image/flavor IDs."""


class BaseImageArtifacts(StrictModel):
    """Managed base-image policy tree."""

    cpu: CpuArtifact = Field(description="Shared CPU policy for all managed CPU workbenches.")
    cuda: CudaFlavors = Field(
        title="CUDA flavors",
        description="CUDA flavor map keyed by image/flavor ID (open keys; sync enforces the managed inventory).",
        json_schema_extra={
            "propertyNames": {"type": "string", "minLength": 1},
            "minProperties": 1,
        },
    )
    rocm: RocmFlavors = Field(
        title="ROCm flavors",
        description="ROCm flavor map keyed by image/flavor ID (open keys; sync enforces the managed inventory).",
        json_schema_extra={
            "propertyNames": {"type": "string", "minLength": 1},
            "minProperties": 1,
        },
    )


class Artifacts(StrictModel):
    """Artifact groups managed by the versions sync flow."""

    base_image: BaseImageArtifacts


class VersionsConfig(StrictModel):
    """Top-level ``versions_config.yml`` document (``schema_version: 1``)."""

    schema_version: SchemaVersion = Field(
        title="Schema version",
        description="Config schema revision; only version 1 is supported today.",
    )
    release: Release
    artifacts: Artifacts


_VERSIONS_CONFIG_ADAPTER = TypeAdapter(VersionsConfig)


def build_json_schema() -> dict[str, Any]:
    """Build the JSON Schema document for ``versions_config.yml``."""
    schema = _VERSIONS_CONFIG_ADAPTER.json_schema(schema_generator=GenerateJsonSchema)
    example = {
        "schema_version": 1,
        "release": {
            "full_version": "3.5.0",
            "rhds_os_base": "el9.6",
            "python_version": "3.12",
            "aipcc_wheel_index": {"stream": "3.5-EA2", "use_test": True},
        },
        "artifacts": {
            "base_image": {
                "cpu": {
                    "rhds": {"channel": "fast", "version": "<full_version>"},
                    "odh": {"origin": "in-house", "version": "latest"},
                },
                "cuda": {
                    "minimal": {
                        "acc_version": "13.0",
                        "rhds": {"channel": "fast"},
                        "odh": {"origin": "in-house"},
                    }
                },
                "rocm": {
                    "minimal": {
                        "acc_version": "7.14",
                        "rhds": {"channel": "fast"},
                        "odh": {"origin": "in-house"},
                    }
                },
            }
        },
    }
    _VERSIONS_CONFIG_ADAPTER.validate_python(example)  # fail fast if example drifts from the model
    return {
        "$schema": GenerateJsonSchema.schema_dialect,
        "$id": SCHEMA_ID,
        **schema,
        "examples": [example],
    }


def main() -> None:
    """Generate the JSON schema for versions_config.yml."""
    out = Path(__file__).parent / "versions_config.schema.json"
    with out.open("w", encoding="utf-8") as handle:
        json.dump(build_json_schema(), handle, indent=2)
        handle.write("\n")
    print(f"Schema generated: {out}")


if __name__ == "__main__":
    main()
