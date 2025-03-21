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
import re
import subprocess
import uuid

import yaml

from enum import Enum

# Path to the file with image references to the image registry
PARAMS_ENV_PATH = "manifests/base/params.env"

class ANNOTATION_TYPE(Enum):
    SOFTWARE = "software"
    PYTHON_DEPS = "python-deps"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)
prune_podman_data = False

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
    """Extracts a variable name from a string (e.g.: '$(odh-rstudio-notebook-image-commit-n-1)') using regex."""

    match = re.search(r"\((.*?)\)", reference)
    return match.group(1) if match else None

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
        result = subprocess.run(["podman", "run", "-d", "--name", container_name, image_link], capture_output=True, text=True, check=True)
        container_id = result.stdout.strip()
        log.info(f"Container '{container_id}' started (detached).")
        return container_id
    except (subprocess.CalledProcessError, FileNotFoundError, Exception) as e:
        log.error(f"Error running Podman container '{image_link}': {e}")
        return None

def execute_command_in_container(container_id, command):
    """Executes a command inside a running Podman container."""

    try:
        result = subprocess.run(["podman", "exec", container_id] + command, capture_output=True, text=True, check=True)
        log.debug(result.stdout.strip())
        return result.stdout.strip()
    except (subprocess.CalledProcessError, Exception) as e:
        log.error(f"Error executing command '{command}' in container '{container_id}': {e}")
        return None

def stop_and_remove_container(container_id):
    """Stops and removes a Podman container."""

    if not container_id:
        log.error(f"Given undefined value in 'container_id' argument!")
        return 1
    try:
        subprocess.run(["podman", "stop", container_id], check=True)
        subprocess.run(["podman", "rm", container_id], check=True)
        if prune_podman_data:
            subprocess.run(["podman", "system", "prune", "--all", "--force"], check=True)
        log.info(f"Container {container_id} stopped and removed.")
    except (subprocess.CalledProcessError, Exception) as e:
        log.error(f"Error stopping/removing container '{container_id}': {e}")
        return 1

    return 0

def parse_json_string(json_string):
    """Parses a JSON string and returns the data as a list of dictionaries."""

    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, Exception) as e:
        log.error(f"Error parsing JSON: {e}")
        return None

def process_dependency_item(item, container_id, annotation_type):
    """Processes a single item (dictionary) from the JSON data."""

    name, version = item.get("name"), item.get("version")
    if not name or not version:
        log.error(f"Missing name or version in item: {item}")
        return 1

    log.info(f"Checking {name} (version {version}) in container...")

    command_mapping = {
        "PyTorch": ["/bin/bash", "-c", f"pip show torch | grep 'Version: '"],
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
        if annotation_type == ANNOTATION_TYPE.SOFTWARE:
            command = ["/bin/bash", "-c", f"{name.lower()} --version"]
        else:
            command = ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"]

    output = execute_command_in_container(container_id, command)

    if output and version.lstrip('v') in output:
        log.info(f"{name} version check passed.")
    else:
        log.error(f"{name} version check failed. Expected '{version}', found '{output}'.")
        return 1

    return 0

def process_tag(tag):
    ret_code = 0

    tag_annotations = tag.get("annotations", {})

    if "name" not in tag:
        log.error(f"Missing 'name' field for {tag}!")
        return 1

    log.info(f"Processing tag: {tag['name']}.")
    outdated_annotation = "opendatahub.io/image-tag-outdated"
    if tag_annotations.get(outdated_annotation) == "true":
        log.info(f"Skipping processing of this tag as it is marked as outdated.")
        print_delimiter()
        return 0
    if "from" not in tag or "name" not in tag["from"]:
        log.error(f"Missing 'from.name' in tag {tag['name']}")
        return 1

    image_ref = tag["from"]["name"]
    image_var = extract_variable(image_ref)
    image_val = get_variable_value(image_var)
    log.debug(f"Retrieved image link: '{image_val}'")

    if not image_val:
        log.error(f"Failed to parse image value reference pointing by '{image_ref}'!")
        return 1

    container_id = run_podman_container(image_var, image_val)
    if not container_id:
        log.error(f"Failed to start a container from image '{image_val}' for the '{image_ref}' tag!")
        return 1

    ntb_sw_annotation = "opendatahub.io/notebook-software"
    python_dep_annotation = "opendatahub.io/notebook-python-dependencies"

    try:
        software = tag_annotations.get(ntb_sw_annotation)
        if not software:
            log.error(f"Missing '{ntb_sw_annotation}' in ImageStream tag '{tag}'!")
            return 1

        python_deps = tag_annotations.get(python_dep_annotation)
        if not python_deps:
            log.error(f"Missing '{python_dep_annotation}' in ImageStream tag '{tag}'!")
            return 1

        for item in parse_json_string(software) or []:
            if process_dependency_item(item, container_id, ANNOTATION_TYPE.SOFTWARE) != 0:
                log.error(f"Failed check for the '{image_ref}' tag!")
                ret_code = 1

        for item in parse_json_string(python_deps) or []:
            if process_dependency_item(item, container_id, ANNOTATION_TYPE.PYTHON_DEPS) != 0:
                log.error(f"Failed check for the '{image_ref}' tag!")
                ret_code = 1
    finally:
        if stop_and_remove_container(container_id) != 0:
            log.error(f"Failed to stop/remove the container '{container_id}' for the '{image_ref}' tag!")
            print_delimiter()
            return 1
        print_delimiter()

    return ret_code

def process_imagestream(imagestream):
    """Processes a single ImageStream file and check images that it is referencing."""

    ret_code = 0
    log.info(f"Processing ImageStream: {imagestream}.")

    yaml_data = load_yaml(imagestream)
    if not yaml_data or "spec" not in yaml_data or "tags" not in yaml_data["spec"]:
        log.error(f"Invalid YAML in {imagestream} as ImageStream file!")
        return 1

    # Process each image version in the ImageStream:
    for tag in yaml_data["spec"]["tags"]:
        if process_tag(tag) != 0:
            log.error(f"Failed to process tag {tag} in ImageStream {imagestream}!")
            # Let's move on the next tag if any
            ret_code = 1
            continue

    return ret_code

def print_delimiter():
    log.info("----------------------------------------------------------------------")
    log.info("")

def main():

    parser = argparse.ArgumentParser(description="Process command-line arguments.")
    parser.add_argument("-p", "--prune-podman-data", action="store_true", help="Prune Podman data after each image is processed. This is useful when running in GHA workers.")

    args = parser.parse_args()
    global prune_podman_data
    prune_podman_data = args.prune_podman_data

    ret_code = 0
    log.info("Starting the check ImageStream software version references.")

    imagestreams = find_imagestream_files()
    log.info("Following list of ImageStream manifests has been found:")
    for imagestream in imagestreams: log.info(imagestream)

    if not imagestreams or len(imagestreams) == 0:
        log.error("Failed to detect any ImageStream manifest files!")
        exit(1)

    print_delimiter()

    for imagestream in imagestreams:
        if process_imagestream(imagestream) != 0:
            log.error(f"Failed to process {imagestream} ImageStream manifest file!")
            # Let's move on the next imagestream if any
            ret_code = 1
            continue

    if ret_code == 0:
        log.info("The software versions check in manifests was successful. Congrats! :)")
    else:
        log.error("The software version check failed, see errors above in the log for more information!")

    exit(ret_code)

if __name__ == "__main__":
    main()
