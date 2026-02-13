import logging
import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field

logger = logging.getLogger(__name__)


class SkopeoConfigLayer(BaseModel):
    """Represents the nested 'config' dictionary in skopeo output."""

    labels: dict[str, str] | None = Field(default=None, alias="Labels")


class SkopeoInspectResult(BaseModel):
    """
    Model for the output of 'skopeo inspect --config'.
    Handles both modern (nested) and legacy (root) label locations.
    """

    # Allow looking up fields by alias (e.g., "Labels" maps to "root_labels")
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    config: SkopeoConfigLayer | None = None

    # Alias handles the "Labels" key if it appears at the root
    root_labels: dict[str, str] | None = Field(default=None, alias="Labels")

    @computed_field
    @property
    def final_labels(self) -> dict[str, str] | None:
        """
        Logic to resolve labels: Check config.Labels first, fallback to root Labels.
        """
        if self.config and self.config.labels is not None:
            return self.config.labels
        return self.root_labels


def get_image_labels(image_name: str) -> dict[str, Any] | None:
    """
    Orchestrates retrieving the config and extracting labels.
    Returns a standard dict or None.
    """
    result_model = get_image_config_model(image_name)

    if result_model and result_model.final_labels is not None:
        logger.info(f"Skopeo successfully inspected {image_name}. Labels: {result_model.final_labels}")
        return result_model.final_labels

    if result_model:
        logger.warning(f"Skopeo inspection for {image_name} found config but no 'Labels' field.")

    return None


def get_image_config_model(image_name: str) -> SkopeoInspectResult | None:
    """
    Runs skopeo and returns a validated Pydantic model.
    """
    skopeo_command = [
        "skopeo",
        "inspect",
        "--override-os=linux",
        "--override-arch=amd64",
        "--config",
        f"docker://{image_name}",
    ]

    try:
        logger.info(f"Attempting remote inspection for {image_name} using skopeo: {' '.join(skopeo_command)}")

        process_result = subprocess.run(skopeo_command, capture_output=True, text=True, check=True, timeout=60)

        # This is faster and safer than json.loads() + dict access
        return SkopeoInspectResult.model_validate_json(process_result.stdout)

    except ValidationError as e:
        logger.warning(f"Failed to validate skopeo output structure for {image_name}: {e}")
    except FileNotFoundError:
        logger.warning("skopeo command not found. Cannot inspect remote image labels.")
    except subprocess.TimeoutExpired:
        logger.warning(f"skopeo inspect for {image_name} timed out.")
    except subprocess.CalledProcessError as e:
        # use e.cmd (list) directly or join carefully for logs
        cmd_str = " ".join(e.cmd) if isinstance(e.cmd, list) else e.cmd
        logger.warning(f"skopeo inspect failed for {image_name}. Command: '{cmd_str}'. Error: {e.stderr.strip()}")

    return None
