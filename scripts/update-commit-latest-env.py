import asyncio
import json
import logging
import pathlib
import re
import typing

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


async def get_image_vcs_ref(image_url: str) -> tuple[str, str | None]:
    """
    Asynchronously inspects a container image's configuration using skopeo
    and extracts the 'vcs-ref' label.

    Args:
        image_url: The full URL of the image to inspect
                   (e.g., 'quay.io/opendatahub/workbench-images@sha256:...').

    Returns:
        A tuple containing the original image_url and the value of the 'vcs-ref'
        label if found, otherwise None.
    """
    # Using 'docker://' prefix is required for skopeo to identify the transport.
    full_image_url = f"docker://{image_url}"

    # Use 'inspect --config' which is much faster as it only fetches the config blob.
    command = ["skopeo", "inspect", "--config", full_image_url]

    logging.info(f"Starting config inspection for: {image_url}")

    try:
        # Create an asynchronous subprocess
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for the command to complete and capture output
        stdout, stderr = await process.communicate()

        # Check for errors
        if process.returncode != 0:
            logging.error(f"Skopeo command failed for {image_url} with exit code {process.returncode}.")
            logging.error(f"Stderr: {stderr.decode().strip()}")
            return image_url, None

        # Decode and parse the JSON output from stdout
        # The output of 'inspect --config' is the image config JSON directly.
        image_config = json.loads(stdout.decode())

        # Safely extract the 'vcs-ref' label from the config's 'Labels'
        vcs_ref = image_config.get("config", {}).get("Labels", {}).get("vcs-ref")

        if vcs_ref:
            logging.info(f"Successfully found 'vcs-ref' for {image_url}: {vcs_ref}")
        else:
            logging.warning(f"'vcs-ref' label not found for {image_url}.")

        return image_url, vcs_ref

    except FileNotFoundError:
        logging.error("The 'skopeo' command was not found. Please ensure it is installed and in your PATH.")
        return image_url, None
    except json.JSONDecodeError:
        logging.error(f"Failed to parse skopeo output as JSON for {image_url}.")
        return image_url, None
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing {image_url}: {e}")
        return image_url, None


async def inspect(images_to_inspect: typing.Iterable[str]) -> list[tuple[str, str | None]]:
    ""
    """
    Main function to orchestrate the concurrent inspection of multiple images.
    """
    tasks = [get_image_vcs_ref(image) for image in images_to_inspect]
    return await asyncio.gather(*tasks)


async def main():
    with open(PROJECT_ROOT / "manifests/base/params-latest.env", "rt") as file:
        images_to_inspect: list[list[str]] = [line.strip().split('=', 1) for line in file.readlines()
                                              if line.strip() and not line.strip().startswith("#")]

    results = await inspect(value for _, value in images_to_inspect)
    output = []
    for image, result in zip(images_to_inspect, results):
        variable, image_digest = image
        _, commit_hash = result
        output.append((re.sub(r'-n$', "-commit-n", variable), commit_hash[:7]))

    with open(PROJECT_ROOT / "manifests/base/commit-latest.env", "wt") as file:
        for line in output:
            print(*line, file=file, sep="=", end="\n")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    asyncio.run(main())
