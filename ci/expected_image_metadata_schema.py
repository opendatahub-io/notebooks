"""Pydantic model for ci/expected-image-metadata.yaml and schema generator."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, RootModel
from pydantic.json_schema import GenerateJsonSchema


class VariantSizes(BaseModel):
    """Per-variant image sizes when ODH and RHOAI differ."""

    model_config = {"extra": "forbid"}

    odh: int | None = Field(default=None, ge=1, description="Compressed image size in MB for ODH")
    rhoai: int | None = Field(default=None, ge=1, description="Compressed image size in MB for RHOAI")


class VariantNames(BaseModel):
    """Per-variant image names when ODH and RHOAI differ."""

    model_config = {"extra": "forbid"}

    odh: str | None = Field(default=None, description="Image name label for ODH")
    rhoai: str | None = Field(default=None, description="Image name label for RHOAI")


class ImageEntry(BaseModel):
    """Expected metadata for a single params.env image variable."""

    model_config = {"extra": "forbid"}

    name: str | VariantNames = Field(
        description="Expected image name label, or per-variant dict when ODH and RHOAI differ."
    )
    commitref: str = Field(description="Expected git branch (e.g. 'main', 'release-2024b').")
    build_name: str = Field(description="Expected OPENSHIFT_BUILD_NAME or 'konflux' for Konflux builds.")
    size_mb: int | VariantSizes = Field(
        description="Expected compressed image size in MB, or per-variant dict. Validated with 10%/100MB tolerance."
    )
    variants: list[Literal["odh", "rhoai"]] = Field(
        min_length=1, description="Which manifest variants include this image."
    )


class ImageMetadataFile(RootModel[dict[str, ImageEntry]]):
    """Top-level schema: variable name → expected image metadata."""


def main():
    """Generate the JSON schema for expected-image-metadata.yaml."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    out = Path(__file__).parent / "expected-image-metadata.schema.json"
    schema = {
        "$schema": GenerateJsonSchema.schema_dialect,
        **ImageMetadataFile.model_json_schema(schema_generator=GenerateJsonSchema),
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")

    print(f"Schema generated: {out}")


if __name__ == "__main__":
    main()
