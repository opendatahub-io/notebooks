# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Copr package rebuild tool."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
