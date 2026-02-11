# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Copr package rebuild tool."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic.json_schema import GenerateJsonSchema


class PackageEntry(BaseModel):
    """A single entry in the rebuild manifest."""

    name: str = Field(description="Source package name (e.g. 'hdf5')")
    nvr: str = Field(description="Fedora Name-Version-Release (e.g. 'hdf5-1.14.6-7.fc44')")
    note: str = Field(default="", description="Human-readable note about why this package is needed")


class Manifest(BaseModel):
    """Declarative manifest of packages to rebuild on Copr."""

    copr_project: str = Field(description="Copr project in owner/name format (e.g. 'opendatahub/rhelai-el9')")
    koji_tag: str = Field(default="f44", description="Fedora tag to pull SRPMs from")
    packages: list[PackageEntry] = Field(description="List of packages to rebuild")
    chroots: list[str] = Field(
        default_factory=list,
        description="Copr chroot names to configure (e.g. ['centos-stream-9-x86_64'])",
    )
    chroot_packages: list[str] = Field(
        default_factory=list,
        description="Extra packages to install in the mock buildroot (e.g. ['autoconf-latest'])",
    )
    build_timeout: int | None = Field(
        default=None,
        description="Build timeout in seconds passed to copr-cli build --timeout (default: Copr's 5h)",
    )


class PackageMetadata(BaseModel):
    """Metadata about a source package retrieved from Koji."""

    name: str = Field(description="Source package name")
    nvr: str = Field(description="Name-Version-Release string")
    srpm_id: int = Field(description="Koji RPM ID of the SRPM")
    srpm_url: str = Field(description="Download URL for the SRPM")
    provides: frozenset[str] = Field(description="Capabilities provided by all binary subpackages")
    build_requires: frozenset[str] = Field(description="BuildRequires from the SRPM")

    model_config = {"frozen": True}


class BuildWave(BaseModel):
    """A group of packages that can be built in parallel."""

    index: int = Field(description="Wave number (0-based)")
    packages: list[str] = Field(description="Source package names in this wave")

    model_config = {"frozen": True}


class BuildResult(BaseModel):
    """Result of a single Copr build."""

    package_name: str
    build_id: int
    status: str = Field(description="Build status: 'succeeded', 'failed', or 'canceled'")
    srpm_url: str


def main():
    """Generate the JSON schema for the Manifest model."""
    import json

    schema = {
        "$schema": GenerateJsonSchema.schema_dialect,
        **Manifest.model_json_schema(schema_generator=GenerateJsonSchema)
    }

    with open("manifest_schema.json", "w") as f:
        json.dump(schema, f, indent=2)

    print("Schema generated: manifest_schema.json")


if __name__ == "__main__":
    main()
