import json
import logging
import subprocess

logger = logging.getLogger(__name__)

type JSON = dict[str, JSON] | list[JSON] | str | int | float | bool | None


def get_image_labels(image_name: str) -> JSON | None:
    try:
        skopeo_command = [
            "skopeo",
            # "--override-os=linux", "--override-arch=amd64",
            "inspect",
            "--config",
            f"docker://{image_name}",
        ]
        logger.info(f"Attempting remote inspection for {image_name} using skopeo: {' '.join(skopeo_command)}")
        result = subprocess.run(skopeo_command, capture_output=True, text=True, check=True, timeout=60)
        image_config_json = json.loads(result.stdout)

        # Labels can be in image_config_json.config.Labels or image_config_json.Labels (older formats)
        labels = image_config_json.get("config", {}).get("Labels")
        if labels is None:
            labels = image_config_json.get("Labels")

        if labels is not None:  # Explicitly check for None, as {} is a valid (empty) set of labels
            logger.info(f"Skopeo successfully inspected {image_name}. Labels: {labels}")
            return labels
        else:
            logger.warning(f"Skopeo inspection for {image_name} found config but no 'Labels' field.")
            return None

    except FileNotFoundError:
        logger.warning("skopeo command not found. Cannot inspect remote image labels without pulling.")
    except subprocess.TimeoutExpired:
        logger.warning(f"skopeo inspect for {image_name} timed out.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"skopeo inspect for {image_name} failed. Command: '{' '.join(e.cmd)}'. Error: {e.stderr}")
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse skopeo JSON output for {image_name}: {e}")
    return None
