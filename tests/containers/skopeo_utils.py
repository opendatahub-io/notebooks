import logging
import re
import subprocess

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field

logger = logging.getLogger(__name__)


class HistoryLayer(BaseModel):
    """Represents a single layer in the image history."""

    created_by: str | None = None
    empty_layer: bool = False


class SkopeoConfigLayer(BaseModel):
    """Represents the 'config' dictionary in skopeo output."""

    model_config = ConfigDict(populate_by_name=True)

    # Raw ENV is a list of "KEY=VALUE" strings
    env_raw: list[str] = Field(default=[], alias="Env")

    # Labels map
    labels: dict[str, str] = Field(default={}, alias="Labels")

    @computed_field
    @property
    def env_dict(self) -> dict[str, str]:
        """Parses the raw ['KEY=VAL', ...] list into a usable dictionary."""
        parsed_env = {}
        for item in self.env_raw:
            if "=" in item:
                # Split only on the first '=' to preserve '=' in values (e.g. base64)
                key, value = item.split("=", 1)
                parsed_env[key] = value
        return parsed_env


class SkopeoInspectResult(BaseModel):
    """Root model for 'skopeo inspect --config'."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    config: SkopeoConfigLayer | None = None
    history: list[HistoryLayer] = []

    # Handle Legacy Labels at root
    root_labels: dict[str, str] | None = Field(default=None, alias="Labels")

    @computed_field
    @property
    def labels(self) -> dict[str, str]:
        """Consolidates config.Labels and root Labels."""
        if self.config and self.config.labels:
            return self.config.labels
        return self.root_labels or {}

    @computed_field
    @property
    def env(self) -> dict[str, str]:
        """Short-circuit accessor for Environment variables."""
        return self.config.env_dict if self.config else {}

    @computed_field
    @property
    def build_args(self) -> dict[str, str | None]:
        """
        Extracts ARGs from the build history commands.
        Note: This returns the declared ARGs. Values are rarely preserved
        in history unless explicitly set like 'ARG FOO=bar'.
        """
        args_found = {}
        # Regex to capture "ARG KEY" or "ARG KEY=VALUE"
        # It looks for the pattern "ARG " followed by keys
        arg_pattern = re.compile(r'ARG\s+([A-Z_0-9]+)(?:=([^"\'\s]+))?')

        for layer in self.history:
            if not layer.created_by:
                continue

            # Search for ARG instructions in the command string
            matches = arg_pattern.findall(layer.created_by)
            for key, value in matches:
                # If value is empty string (just "ARG KEY"), store None
                args_found[key] = value if value else None

        return args_found


def get_image_info(image_name: str) -> SkopeoInspectResult | None:
    """Runs skopeo and returns a validated Pydantic model."""
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
        image_data = SkopeoInspectResult.model_validate_json(process_result.stdout)

        logger.info(f"Loaded {len(image_data.labels)} labels and {len(image_data.env)} env vars.")
        return image_data

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
