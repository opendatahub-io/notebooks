#!/usr/bin/python3
#
# This script iterates over the ImageStreams in our manifest files and for each image version
# there it checks the given information about expected installed software with the actual
# reality of each such image.
#
# Usage:
#     python ./ci/check-software-versions.py
#
# The script is expected to be executed from the root directory of this repository.
#

import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
from enum import Enum

import yaml

# Path to the file with image references to the image registry
PARAMS_ENV_PATH = "manifests/base/params.env"


class AnnotationType(Enum):
    SOFTWARE = "software"
    PYTHON_DEPS = "python-deps"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)
prune_podman_data = False


def raise_exception(error_msg):
    log.error(error_msg)
    raise Exception(error_msg)

def find_imagestream_files(directory="."):
    """Finds all ImageStream YAML files in the given directory and its subdirectories."""

    imagestreams = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith("-imagestream.yaml") and not file.startswith("runtime-"):
                imagestreams.append(os.path.join(root, file))
    imagestreams.sort()
    return imagestreams


def load_yaml(filepath):
    """Loads and parses a YAML file."""

    try:
        with open(filepath, "r") as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        log.error(f"Loading YAML from '{filepath}': {e}")
        return None


def extract_variable(reference):
    """Extracts a variable name from a string (e.g.: 'odh-rstudio-notebook-image-commit-n-1_PLACEHOLDER') using regex."""

    return reference.replace("_PLACEHOLDER", "")


def get_variable_value(variable_name, params_file_path=PARAMS_ENV_PATH):
    """Retrieves the value of a variable from a parameters file."""

    try:
        with open(params_file_path, "r") as params_file:
            for line in params_file:
                if variable_name in line:
                    return line.split("=")[1].strip()
        log.error(f"Variable '{variable_name}' not found in '{params_file_path}'!")
        return None
    except FileNotFoundError:
        log.error(f"'{params_file_path}' not found!")
        return None
    except Exception as e:
        log.error(f"An unexpected error occurred: {e}")
        return None


def run_podman_container(image_name, image_link, detach=True):
    """Runs a Podman container in detached mode and returns the container ID."""

    try:
        if prune_podman_data:
            # Since we're pruning the data, we're probably interested about current disk space usage.
            subprocess.run(["df", "-h"], check=True)
        container_name = f"tmp-{image_name}-{uuid.uuid4()}"
        result = subprocess.run(
            ["podman", "run", "-d", "--name", container_name, image_link], capture_output=True, text=True, check=True
        )
        container_id = result.stdout.strip()
        log.info(f"Container '{container_id}' started (detached).")
        return container_id
    except (subprocess.CalledProcessError, FileNotFoundError, Exception) as e:
        log.error(f"Error running Podman container '{image_link}': {e}")
        return None


def execute_command_in_container(container_id, command):
    """Executes a command inside a running Podman container."""

    try:
        result = subprocess.run(["podman", "exec", container_id, *command], capture_output=True, text=True, check=True)
        log.debug(result.stdout.strip())
        return result.stdout.strip()
    except (subprocess.CalledProcessError, Exception) as e:
        log.error(f"Error executing command '{command}' in container '{container_id}': {e}")
        return None


def stop_and_remove_container(container_id):
    """Stops and removes a Podman container."""

    if not container_id:
        raise_exception("Given undefined value in 'container_id' argument!")
    try:
        subprocess.run(["podman", "stop", container_id], check=True)
        subprocess.run(["podman", "rm", container_id], check=True)
        if prune_podman_data:
            subprocess.run(["podman", "system", "prune", "--all", "--force"], check=True)
        log.info(f"Container {container_id} stopped and removed.")
    except (subprocess.CalledProcessError, Exception) as e:
        raise_exception(f"Error stopping/removing container '{container_id}': {e}")


def parse_json_string(json_string):
    """Parses a JSON string and returns the data as a list of dictionaries."""

    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, Exception) as e:
        raise_exception(f"Error parsing JSON: {e}")


import subprocess
import time
import sys
import os

def download_sbom_with_retry(platform_arg: str, image_url: str, sbom: str):
    """
    Downloads an SBOM with retry logic

    Args:
        platform_arg: The platform argument for the cosign command.
        image_url: The URL of the image to download the SBOM for.
        sbom: The path to the file where the SBOM should be saved.
    """
    # TODO improve by ./cosign tree image and check for the "SBOMs" string - if present, the sboms is there, if missing it's not there
    max_try = 5
    wait_sec = 2
    status = -1
    err_file = "err"  # Temporary file to store stderr
    command_bin = "cosign"

    for run in range(1, max_try + 1):
        status = 0
        command = [
            command_bin,
            "download",
            "sbom",
            platform_arg,
            image_url,
        ]

        try:
            with open(sbom, "w") as outfile, open(err_file, "w") as errfile:
                result = subprocess.run(
                    command,
                    stdout=outfile,
                    stderr=errfile,
                    check=False  # Don't raise an exception on non-zero exit code
                )
                status = result.returncode
        except FileNotFoundError:
            print(f"Error: The '{command_bin}' command was not found. Make sure it's in your PATH or the current directory.", file=sys.stderr)
            return

        if status == 0:
            break
        else:
            print(f"Attempt {run} failed with status {status}. Retrying in {wait_sec} seconds...", file=sys.stderr)
            time.sleep(wait_sec)

    if status != 0:
        print(f"Failed to get SBOM after {max_try} tries", file=sys.stderr)
        try:
            with open(err_file, "r") as f:
                error_output = f.read()
                print(error_output, file=sys.stderr)
        except FileNotFoundError:
            print(f"Error file '{err_file}' not found.", file=sys.stderr)
        finally:
            raise_exception(f"SBOM download failed!")
    else:
        print(f"Successfully downloaded SBOM to: {sbom}")

    # Clean up the temporary error file
    if os.path.exists(err_file):
        os.remove(err_file)


def process_dependency_item(item, container_id, annotation_type):
    """Processes a single item (dictionary) from the JSON data."""

    name, version = item.get("name"), item.get("version")
    if not name or not version:
        raise_exception(f"Missing name or version in item: {item}")

    log.info(f"Checking {name} (version {version}) in container...")

    command_mapping = {
        "PyTorch": ["/bin/bash", "-c", "pip show torch | grep 'Version: '"],
        "ROCm": ["/bin/bash", "-c", "rpm -q --queryformat '%{VERSION}\n' rocm-core"],
        "ROCm-PyTorch": ["/bin/bash", "-c", "pip show torch | grep 'Version: ' | grep rocm"],
        "ROCm-TensorFlow": ["/bin/bash", "-c", "pip show tensorflow-rocm | grep 'Version: '"],
        "TensorFlow": ["/bin/bash", "-c", "pip show tensorflow | grep 'Version: '"],
        "R": ["/bin/bash", "-c", "R --version"],
        "rstudio-server": ["/bin/bash", "-c", "rpm -q --queryformat '%{VERSION}\n' rstudio-server"],
        "Sklearn-onnx": ["/bin/bash", "-c", "pip show skl2onnx | grep 'Version: '"],
        "MySQL Connector/Python": ["/bin/bash", "-c", "pip show mysql-connector-python | grep 'Version: '"],
        "Nvidia-CUDA-CU12-Bundle": ["/bin/bash", "-c", "pip show nvidia-cuda-runtime-cu12 | grep 'Version: '"],
        "Python": ["/bin/bash", "-c", "python --version"],
        "CUDA": ["/bin/bash", "-c", "nvcc --version"],
    }

    command = command_mapping.get(name)
    if not command:
        if annotation_type == AnnotationType.SOFTWARE:
            command = ["/bin/bash", "-c", f"{name.lower()} --version"]
        else:
            command = ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"]

    output = execute_command_in_container(container_id, command)

    if output and version.lstrip("v") in output:
        log.info(f"{name} version check passed.")
    else:
        raise_exception(f"{name} version check failed. Expected '{version}', found '{output}'.")


def check_sbom_available(image):
    # TODO
    return True


def load_json_file(filepath):
    """
    Loads data from a JSON file.

    Args:
        filepath (str): The path to the JSON file.

    Returns:
        dict or list: The data loaded from the JSON file,
                    or None if an error occurs.
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def find_item_in_array_by_name(json_data, array_key, target_name):
  """
  Finds an item in a JSON array (list of dictionaries) by matching a 'name' value.

  Args:
    json_data (dict or list): The loaded JSON data.
    array_key (str): The key in json_data that holds the array.
    target_name (str): The value of the 'name' key to search for.

  Returns:
    dict or None: The dictionary item if found, otherwise None.
  """
  if isinstance(json_data, dict) and array_key in json_data:
    data_array = json_data[array_key]
    if isinstance(data_array, list):
      for item in data_array:
        # Check if the item is a dictionary and has a 'name' key
        if isinstance(item, dict) and 'name' in item:
          if item['name'] == target_name:
            return item  # Return the first matching item
  return None # Return None if the array or item is not found


def check_sbom_item(item, sbom_file):
    name, version = item.get("name"), item.get("version")
    if not name or not version:
        raise_exception(f"Missing name or version in item: {item}")

    log.info(f"Checking {name} (version {version}) in given SBOM file: {sbom_file}")
    sbom_data = load_json_file(sbom_file)

    if sbom_data:
        print(f"Successfully loaded JSON data from {sbom_file}")
    else:
        raise_exception(f"Can't load JSON data from {sbom_file}!")

    sbom_item = find_item_in_array_by_name(sbom_data, "packages", name)

    if sbom_item == None:
        raise_exception(f"Can't find the package record for the {name} in the SBOM file!")

    sbom_version = sbom_item["versionInfo"]
    if version not in sbom_version:
        raise_exception(f"The version in the manifest ({version}) doesn't match the data in the SBOM file ({sbom_version})!")


def check_against_image(tag, tag_annotations, tag_name, image):
    ntb_sw_annotation = "opendatahub.io/notebook-software"
    python_dep_annotation = "opendatahub.io/notebook-python-dependencies"

    try:
        software = tag_annotations.get(ntb_sw_annotation)
        if not software:
            raise_exception(f"Missing '{ntb_sw_annotation}' in ImageStream tag '{tag}'!")

        python_deps = tag_annotations.get(python_dep_annotation)
        if not python_deps:
            raise_exception(f"Missing '{python_dep_annotation}' in ImageStream tag '{tag}'!")
    finally:
        print_delimiter()

    # Check if the sbom for the image is available
    sbom_downloaded = False
    output_file = "sbom.json"
    if check_sbom_available:
        log.info(f"SBOM for image '{image}' is available.")
        platform = "--platform=linux/amd64"
        download_sbom_with_retry(platform, image, output_file)
        sbom_downloaded = True

    container_id = 0
    if sbom_downloaded == False:
        # SBOM not available -> gather data directly from the running image
        container_id = run_podman_container(f"{tag_name}-container", image)
        if not container_id:
            raise_exception(f"Failed to start a container from image '{image}' for the '{tag_name}' tag!")

    errors = []
    try:
        try:
            for item in parse_json_string(software) or []:
                if sbom_downloaded == True:
                    check_sbom_content(software, python_deps, output_file)
                else:
                    process_dependency_item(item, container_id, AnnotationType.SOFTWARE)
        except Exception as e:
            log.error(f"Failed check for the '{tag_name}' tag!")
            errors.append(str(e))

        try:
            for item in parse_json_string(python_deps) or []:
                if sbom_downloaded == True:
                    check_sbom_content(software, python_deps, output_file)
                else:
                    process_dependency_item(item, container_id, AnnotationType.PYTHON_DEPS)
        except Exception as e:
            log.error(f"Failed check for the '{tag_name}' tag!")
            errors.append(str(e))
    finally:
        print_delimiter()
        if sbom_downloaded == False:
            try:
                stop_and_remove_container(container_id)
            except Exception as e:
                log.error(f"Failed to stop/remove the container '{container_id}' for the '{tag_name}' tag!")
                errors.append(str(e))

    if errors:
        raise Exception(errors)


def process_tag(tag, image):
    tag_annotations = tag.get("annotations", {})

    if "name" not in tag:
        raise_exception(f"Missing 'name' field for {tag}!")

    log.info(f"Processing tag: {tag['name']}.")
    outdated_annotation = "opendatahub.io/image-tag-outdated"
    if tag_annotations.get(outdated_annotation) == "true":
        log.info("Skipping processing of this tag as it is marked as outdated.")
        print_delimiter()
        return 0
    if "from" not in tag or "name" not in tag["from"]:
        raise_exception(f"Missing 'from.name' in tag {tag['name']}")

    tag_name = tag["from"]["name"]
    if (image == None):
        image_var = extract_variable(tag_name)
        image_val = get_variable_value(image_var)
        log.debug(f"Retrieved image link: '{image_val}'")

        if not image_val:
            raise_exception(f"Failed to parse image value reference pointing by '{tag_name}'!")
    else:
        image_val = image
        log.debug(f"Using the given image link: '{image_val}'")

    # Now, with the image known and the tag with the manifest data, let's compare what is on the image
    check_against_image(tag, tag_annotations, tag_name, image_val)


def process_imagestream(imagestream, image, given_tag):
    """Processes a single ImageStream file and check images that it is referencing."""

    log.info(f"Processing ImageStream: {imagestream}.")

    yaml_data = load_yaml(imagestream)
    if not yaml_data or "spec" not in yaml_data or "tags" not in yaml_data["spec"]:
        raise_exception(f"Invalid YAML content in {imagestream} as ImageStream file!")

    if (given_tag == None):
        tags = yaml_data["spec"]["tags"]
    else:
        tags = given_tag

    # Process each image version in the ImageStream:
    errors = []
    for tag in tags:
        try:
            process_tag(tag, image)
        except Exception as e:
            # We want to continue to process the next tag if possible
            log.error(f"Failed to process tag {tag} in ImageStream {imagestream}!")
            # errors.append(f"{tag}:" + str(e))
            errors.append(f"///:" + str(e))

    if (len(errors) > 0):
        raise Exception(errors)


def print_delimiter():
    log.info("----------------------------------------------------------------------")
    log.info("")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Process command-line arguments.")
    parser.add_argument(
        "-p",
        "--prune-podman-data",
        action="store_true",
        help="Prune Podman data after each image is processed. This is useful when running in GHA workers.",
    )
    group_required = parser.add_argument_group("Explicit image and manifest tag information")
    group_required.add_argument(
        "-i",
        "--image",
        type=str,
        help="Particular image to check.",
    )
    group_required.add_argument(
        "-s",
        "--image-stream",
        type=str,
        help="Particular ImageStream definition selected to check.",
    )
    group_required.add_argument(
        "-t",
        "--tag",
        type=str,
        help="Particular tag name to process from the given ImageStream.",
    )

    args = parser.parse_args()
    prune_podman_data = args.prune_podman_data

    image = args.image
    image_stream = args.image_stream
    tag = args.tag
    # Enforce that image, image_stream and tag arguments are either all set or none are set
    if (image and image_stream and tag) or (not image and not image_stream and not tag):
        if image:
            print(f"Processing the explicitly given image and ImageStream/tag: {image}, {image_stream}, {tag}")
        else:
            print("Running the check against all ImageStreams we'll find.")
    else:
        parser.error("The arguments --image, --image-stream, and --tag must be either all set or none of them should be set.")

    return prune_podman_data, image, image_stream, tag


def main():
    global prune_podman_data  # noqa: PLW0603 Using the global statement to update `prune_podman_data` is discouraged
    prune_podman_data, image, image_stream, tag = parse_arguments()


    log.info(f"{prune_podman_data}, {tag}, {image}, {image_stream}")

    ret_code = 0
    log.info("Starting the check ImageStream software version references.")

    if (image_stream == None):
        imagestreams = find_imagestream_files()
    else:
        imagestreams = [image_stream]

    log.info("Following list of ImageStream manifests will be processed:")
    for imagestream in imagestreams:
        log.info(imagestream)

    if not imagestreams or len(imagestreams) == 0:
        log.error("Failed to detect any ImageStream manifest files!")
        sys.exit(1)

    print_delimiter()

    errors = []
    for imagestream in imagestreams:
        try:
            process_imagestream(imagestream, image, tag)
        except Exception as e:
            log.error(f"Failed to process {imagestream} ImageStream manifest file!")
            errors.append(f"ImageStream path: {imagestream} --- " + str(e))

    print_delimiter()
    log.info("Test results:")

    if len(errors) == 0:
        log.info("The software versions check in manifests was successful. Congrats! :)")
    else:
        for error in errors:
            log.error(error)
        log.error("The software version check failed, see errors above in the log for more information!")

    sys.exit(ret_code)


if __name__ == "__main__":
    main()
