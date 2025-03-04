import os
import re
import subprocess
import yaml

PARAMS_ENV_PATH = "manifests/base/params.env"


def find_imagestream_files(directory="."):
    """Finds all ImageStream YAML files in the given directory and its subdirectories."""
    imagestreams = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith("-imagestream.yaml"):
                imagestreams.append(os.path.join(root, file))
    imagestreams.sort()
    return imagestreams


def load_yaml(filepath):
    """Loads and parses a YAML file."""
    try:
        with open(filepath, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found.")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML in '{filepath}': {e}")
        return None


def extract_variable(reference):
    """Extracts a variable name from a string using regex."""
    match = re.search(r"\((.*?)\)", reference)
    return match.group(1) if match else None


def get_variable_value(variable_name, params_file_path=PARAMS_ENV_PATH):
    """Retrieves the value of a variable from a parameters file."""
    try:
        with open(params_file_path, "r") as params_file:
            for line in params_file:
                if variable_name in line:
                    return line.split("=")[1].strip()
        return None  # Variable not found
    except FileNotFoundError:
        print(f"Error: {params_file_path} not found.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


# def run_podman_command(command):
#     """Executes a Podman command and returns the output."""
#     try:
#         result = subprocess.run(
#             command,
#             capture_output=True,
#             text=True,
#             check=True,  # Raise an exception for non-zero return codes
#         )
#         return result.stdout.strip()
#     except subprocess.CalledProcessError as e:
#         print(f"Podman command failed: {e}")
#         print(f"Stderr: {e.stderr}") #print the error message
#         return None
#     except FileNotFoundError:
#         print("Podman not found. Is it installed and in your PATH?")
#         return None
#     except Exception as e:
#         print(f"An unexpected error occurred: {e}")
#         return None





# import subprocess
# import time
# import uuid

# def run_podman_container(image_name, command=None, detach=False, auto_remove=True):
#     """
#     Runs a Podman container.

#     Args:
#         image_name (str): The name of the container image.
#         command (list, optional): The command to run inside the container. Defaults to None.
#         detach (bool, optional): Run the container in detached mode. Defaults to False.
#         auto_remove (bool, optional): Automatically remove the container after it exits. Defaults to True.

#     Returns:
#         str: The container ID if successful, None otherwise.
#     """
#     container_id = None
#     try:
#         podman_command = ["podman", "run"]
#         if detach:
#             podman_command.append("-d")
#         if auto_remove:
#             podman_command.append("--rm")

#         unique_container_name = f"temp-container-{uuid.uuid4()}"
#         podman_command.extend(["--name", unique_container_name, image_name])

#         if command:
#             podman_command.extend(command)

#         result = subprocess.run(
#             podman_command,
#             capture_output=True,
#             text=True,
#             check=True,
#         )
#         if detach:
#           container_id = result.stdout.strip()
#           print(f"Container {container_id} started in detached mode.")

#         else:
#           print(result.stdout) #print the output of the container.

#         if auto_remove and not detach:
#             print("Container finished and automatically removed.")
#         elif not detach:
#             container_id = subprocess.run(["podman", "ps", "-aqf", f"name={unique_container_name}"], capture_output=True, text=True).stdout.strip()

#         return container_id

#     except subprocess.CalledProcessError as e:
#         print(f"Podman command failed: {e}")
#         print(f"Stderr: {e.stderr}")
#         return None
#     except FileNotFoundError:
#         print("Podman not found. Is it installed and in your PATH?")
#         return None
#     except Exception as e:
#         print(f"An unexpected error occurred: {e}")
#         return None

# def stop_and_remove_container(container_id):
#     """Stops and removes a Podman container."""
#     if not container_id:
#         return

#     try:
#         subprocess.run(["podman", "stop", container_id], check=True)
#         subprocess.run(["podman", "rm", container_id], check=True)
#         print(f"Container {container_id} stopped and removed.")
#     except subprocess.CalledProcessError as e:
#         print(f"Failed to stop/remove container {container_id}: {e}")
#         print(f"Stderr: {e.stderr}")
#     except Exception as e:
#         print(f"An unexpected error occurred: {e}")










import subprocess
import time
import uuid

def run_podman_container(image_name, detach=True):
    """Runs a Podman container in detached mode and returns the container ID."""
    try:
        unique_container_name = f"temp-container-{uuid.uuid4()}"
        result = subprocess.run(
            ["podman", "run", "-d", "--name", unique_container_name, image_name],
            capture_output=True,
            text=True,
            check=True,
        )
        container_id = result.stdout.strip()
        print(f"Container {container_id} started in detached mode.")
        return container_id

    except subprocess.CalledProcessError as e:
        print(f"Podman command failed: {e}")
        print(f"Stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Podman not found. Is it installed and in your PATH?")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def execute_command_in_container(container_id, command):
    """Executes a command inside a running Podman container."""
    try:
        result = subprocess.run(
            ["podman", "exec", container_id] + command,
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command execution failed: {e}")
        print(f"Stderr: {e.stderr}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def stop_and_remove_container(container_id):
    """Stops and removes a Podman container."""
    if not container_id:
        return

    try:
        subprocess.run(["podman", "stop", container_id], check=True)
        subprocess.run(["podman", "rm", container_id], check=True)
        print(f"Container {container_id} stopped and removed.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop/remove container {container_id}: {e}")
        print(f"Stderr: {e.stderr}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")






import json

def parse_json_string(json_string):
    """Parses a JSON string and returns the data as a list of dictionaries."""
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def process_item(item, container_id):
    """Processes a single item (dictionary) from the JSON data."""
    name = item.get("name")
    version = item.get("version")

    if name and version:
        print(f"Name: {name}, Version: {version}")

        if name == "PyTorch":
            name = "torch"
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"])
        elif name == "ROCm":
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", "rpm -q --queryformat '%{VERSION}\n' rocm"])
        elif name == "ROCm-PyTorch":
            name = "torch"
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"])
            assert "rocm" in output
        elif name == "ROCm-TensorFlow":
            name = "tensorflow-rocm"
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"])
        elif name == "TensorFlow":
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"])
        elif name == "R":
            version = version.removeprefix("v")
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"{name} --version"])
        else:
            if name == "Python":
                version = version.removeprefix("v")
            elif name == "CUDA":
                name = "nvcc"

            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"{name.lower()} --version"])

        assert version in output
    else:
        print("Warning: Missing 'name' or 'version' in an item.")

def process_item_python_dep(item, container_id):
    """Processes a single item (dictionary) from the JSON data."""
    name = item.get("name")
    version = item.get("version")

    if name and version:
        print(f"Name: {name}, Version: {version}")

        if name == "rstudio-server":
            output = execute_command_in_container(container_id, ["/bin/bash", "-c", "rpm -q --queryformat '%{VERSION}\n' rstudio-server"])
        else:
            if name == "Sklearn-onnx":
                name = "skl2onnx"
            elif name == "MySQL Connector/Python":
                name = "mysql-connector-python"
            elif name == "PyTorch":
                name = "torch"
            elif name == "ROCm-PyTorch":
                name = "torch"
                output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"])
                assert "rocm" in output
            elif name == "ROCm-TensorFlow":
                name = "tensorflow-rocm"
            elif name == "Nvidia-CUDA-CU12-Bundle":
                name = "nvidia-cuda-runtime-cu12"

            output = execute_command_in_container(container_id, ["/bin/bash", "-c", f"pip show {name.lower()} | grep 'Version: '"])

        assert version in output
    else:
        print("Warning: Missing 'name' or 'version' in an item.")

def iterate_and_process_json(json_string, python_deps, container_id):
    """Iterates over the parsed JSON data and processes each item."""
    data = parse_json_string(json_string)
    if data:
        for item in data:
            process_item(item, container_id)

    data = parse_json_string(python_deps)
    if data:
        for item in data:
            process_item_python_dep(item, container_id)





def process_imagestream(imagestream):
    """Processes a single ImageStream file."""
    print("---------------------------------------------")
    print(f"Processing the '{imagestream}' file.")

    yaml_data = load_yaml(imagestream)
    if not yaml_data or "spec" not in yaml_data or "tags" not in yaml_data["spec"]:
        print(f"ERROR: Invalid or incomplete YAML structure in '{imagestream}'.")
        print("----------------------------------------------------")
        return 1  # Indicate error

    img_versions = [tag["name"] for tag in yaml_data["spec"]["tags"] if "name" in tag]
    if not img_versions:
        print(f"ERROR: Failed to detect any tag version in the '{imagestream}' ImageStream manifest file!")
        print("----------------------------------------------------")
        return 1

    for img_version in img_versions:
        print(f"Processing the '{img_version}' tag in the '{imagestream}'.")

        tag_data = next((tag for tag in yaml_data["spec"]["tags"] if tag.get("name") == img_version), None)
        if not tag_data or "from" not in tag_data or "name" not in tag_data["from"]:
            print(f"ERROR: Failed to find 'from.name' for tag '{img_version}' in '{imagestream}'.")
            print("----------------------------------------------------")
            return 1

        img_reference = tag_data["from"]["name"]
        print(f"Determined image reference variable: '{img_reference}'")

        img_variable = extract_variable(img_reference)
        if not img_variable:
            print(f"ERROR: Could not extract variable from '{img_reference}'")
            return 1

        img_value = get_variable_value(img_variable)
        if img_value is None:
            print(f"ERROR: Variable '{img_variable}' not found in '{PARAMS_ENV_PATH}'")
            return 1

        print(f"Determined image reference value: '{img_value}'")

        if "annotations" in tag_data and "opendatahub.io/notebook-software" in tag_data["annotations"]:
            img_software = tag_data["annotations"]["opendatahub.io/notebook-software"]
            print(f"Determined image software annotation: '{img_software}'")
        else:
            print(f"Warning: 'opendatahub.io/notebook-software' annotation not found for tag '{img_version}'")

        if "annotations" in tag_data and "opendatahub.io/notebook-python-dependencies" in tag_data["annotations"]:
            img_python_deps = tag_data["annotations"]["opendatahub.io/notebook-python-dependencies"]
            print(f"Determined image Python dependencies annotation: '{img_python_deps}'")
        else:
            print(f"Warning: 'opendatahub.io/notebook-python-dependencies' annotation not found for tag '{img_version}'")

        # check_software_versions(img_software, img_value)
        # check_python_dependencies(img_python_deps, img_value)
        # podman_version = run_podman_command(["podman", "--version"])
        # print(podman_version)

        # if container_id:
        #     time.sleep(5) #example sleep, replace with other code.
        #     stop_and_remove_container(container_id)

        # #example of detached mode.
        # image2 = "nginx"
        # container_id2 = run_podman_container(image_name=img_value, detach=True)

        # if container_id2:
        #     time.sleep(10)
        #     stop_and_remove_container(container_id2)

        # #example of running a command inside the container.
        # command3 = ["/bin/bash", "-c", "echo 'Hello from inside the container!'"]
        # run_podman_container(img_value, command=command3)

        # Example usage:
        print("Gonna start a container now...")
        container_id = run_podman_container(img_value)

        if container_id:
            try:
                iterate_and_process_json(img_software, img_python_deps, container_id)
            finally:
                stop_and_remove_container(container_id)

    return 0  # Indicate success


def main():
    """Main function to orchestrate the script."""
    ret_code = 0
    print("Starting the check ImageStream software version references.")
    print("---------------------------------------------")

    imagestreams = find_imagestream_files()
    print("Following list of ImageStream manifests has been found:")
    print("\n".join(imagestreams))

    if not imagestreams:
        print("ERROR: Failed to detect any ImageStream manifest files!")
        print("----------------------------------------------------")
        exit(1)

    for imagestream in imagestreams:
        ret_code = process_imagestream(imagestream) or ret_code
        # exit(0)

    exit(ret_code)


if __name__ == "__main__":
    main()













# import os
# import subprocess
# import re
# import yaml

# ret_code = 0

# print("Starting the check ImageStream software version references.")
# print("---------------------------------------------")

# all_imagestreams = []
# for root, _, files in os.walk("."):
#     for file in files:
#         if file.endswith("-imagestream.yaml"):
#             all_imagestreams.append(os.path.join(root, file))

# all_imagestreams.sort()

# print("Following list of ImageStream manifests has been found:")
# print("\n".join(all_imagestreams))

# if not all_imagestreams:
#     print("ERROR: Failed to detect any ImageStream manifest files!")
#     print("----------------------------------------------------")
#     exit(1)

# PARAMS_ENV_PATH="manifests/base/params.env"

# for imagestream in all_imagestreams:
#     print("---------------------------------------------")
#     print(f"Processing the '{imagestream}' file.")

#     try:
#         with open(imagestream, "r") as f:
#             yaml_data = yaml.safe_load(f)

#         if not yaml_data or "spec" not in yaml_data or "tags" not in yaml_data["spec"]:
#             print(
#                 f"ERROR: Invalid or incomplete YAML structure in '{imagestream}'."
#             )
#             print("----------------------------------------------------")
#             ret_code = 1
#             continue

#         img_versions = [tag["name"] for tag in yaml_data["spec"]["tags"] if "name" in tag]

#         if not img_versions:
#             print(
#                 f"ERROR: Failed to detect any tag version in the '{imagestream}' ImageStream manifest file!"
#             )
#             print("----------------------------------------------------")
#             ret_code = 1
#             continue

#         for img_version in img_versions:
#             print(f"Processing the '{img_version}' tag in the '{imagestream}'.")

#             tag_data = next(
#                 (tag for tag in yaml_data["spec"]["tags"] if tag.get("name") == img_version), None
#             )

#             if not tag_data or "from" not in tag_data or "name" not in tag_data["from"]:
#                 print(
#                     f"ERROR: Failed to find 'from.name' for tag '{img_version}' in '{imagestream}'."
#                 )
#                 print("----------------------------------------------------")
#                 ret_code = 1
#                 continue

#             img_reference = tag_data["from"]["name"]
#             print(f"Determined image reference variable: '{img_reference}'")

#             img_variable_match = re.search(r"\((.*?)\)", img_reference)
#             if not img_variable_match:
#                 print(f"ERROR: Could not extract variable from '{img_reference}'")
#                 ret_code = 1
#                 continue

#             img_variable = img_variable_match.group(1)

#             try:
#                 with open(PARAMS_ENV_PATH, "r") as params_file:
#                     for line in params_file:
#                         if img_variable in line:
#                             img_value = line.split("=")[1].strip()
#                             break
#                         else:
#                             img_value = None

#                 if img_value is None:
#                     print(f"ERROR: Variable '{img_variable}' not found in '{PARAMS_ENV_PATH}'")
#                     ret_code=1
#                     continue

#                 print(f"Determined image reference value: '{img_value}'")

#                 if "annotations" in tag_data and "opendatahub.io/notebook-software" in tag_data["annotations"]:
#                     img_software = tag_data["annotations"]["opendatahub.io/notebook-software"]
#                     print(f"Determined image software annotation: '{img_software}'")
#                 else:
#                     print(f"Warning: 'opendatahub.io/notebook-software' annotation not found for tag '{img_version}'")

#                 if "annotations" in tag_data and "opendatahub.io/notebook-python-dependencies" in tag_data["annotations"]:
#                     img_python_deps = tag_data["annotations"]["opendatahub.io/notebook-python-dependencies"]
#                     print(f"Determined image Python dependencies annotation: '{img_python_deps}'")
#                 else:
#                     print(f"Warning: 'opendatahub.io/notebook-python-dependencies' annotation not found for tag '{img_version}'")
#             except FileNotFoundError:
#                 print(f"Error: {PARAMS_ENV_PATH} not found.")
#                 ret_code = 1
#                 continue
#             except Exception as e:
#                 print(f"An unexpected error occurred: {e}")
#                 ret_code = 1
#                 continue

#     except FileNotFoundError:
#         print(f"Error: ImageStream file '{imagestream}' not found.")
#         ret_code = 1
#         continue
#     except yaml.YAMLError as e:
#         print(f"Error parsing YAML in '{imagestream}': {e}")
#         ret_code = 1
#         continue
#     except Exception as e:
#         print(f"An unexpected error occurred: {e}")
#         ret_code = 1
#         continue

# exit(ret_code)













# for imagestream in all_imagestreams:
#     print("---------------------------------------------")
#     print(f"Processing the '{imagestream}' file.")

#     try:
#         result = subprocess.run(
#             ["yq", "-r", ".spec.tags[].name", imagestream],
#             capture_output=True,
#             text=True,
#             check=True,
#         )
#         img_versions = result.stdout.strip().split("\n")
#     except subprocess.CalledProcessError:
#         print(
#             f"ERROR: Failed to detect any tag version in the '{imagestream}' ImageStream manifest file!"
#         )
#         print("----------------------------------------------------")
#         ret_code = 1
#         continue

#     for img_version in img_versions:
#         print(f"Processing the '{img_version}' tag in the '{imagestream}'.")
#         try:
#             result = subprocess.run(
#                 ["yq", "-r", f".spec.tags[] | select(.name == '{img_version}').from.name", imagestream],
#                 capture_output=True,
#                 text=True,
#                 check=True,
#             )
#             img_reference = result.stdout.strip()
#             print(f"Determined image reference variable: '{img_reference}'")

#             img_variable = re.search(r"\((.*?)\)", img_reference).group(1)

#             with open(PARAMS_ENV_PATH, 'r') as f:
#               for line in f:
#                 if img_variable in line:
#                   img_value=line.split("=")[1].strip()
#                   break;

#             print(f"Determined image reference value: '{img_value}'")

#             result = subprocess.run(
#                 [
#                     "yq",
#                     "-r",
#                     f'.spec.tags[] | select(.name == "{img_version}").annotations."opendatahub.io/notebook-software"',
#                     imagestream,
#                 ],
#                 capture_output=True,
#                 text=True,
#                 check=True,
#             )
#             img_software = result.stdout.strip()
#             print(f"Determined image software annotation: '{img_software}'")

#             result = subprocess.run(
#                 [
#                     "yq",
#                     "-r",
#                     f'.spec.tags[] | select(.name == "{img_version}").annotations."opendatahub.io/notebook-python-dependencies"',
#                     imagestream,
#                 ],
#                 capture_output=True,
#                 text=True,
#                 check=True,
#             )
#             img_python_deps = result.stdout.strip()
#             print(f"Determined image Python dependencies annotation: '{img_python_deps}'")

#         except subprocess.CalledProcessError as e:
#             print(f"Error processing {imagestream} tag {img_version}: {e}")
#             ret_code = 1
#             continue
#         except AttributeError:
#             print(f"Error: Could not extract variable from '{img_reference}'")
#             ret_code = 1
#             continue
#         except FileNotFoundError:
#             print(f"Error: {PARAMS_ENV_PATH} not found.")
#             ret_code = 1
#             continue
#         except Exception as e:
#             print(f"An unexpected error occurred: {e}")
#             ret_code = 1
#             continue

#     #TODO: run that image, for each software version check the version in the image, etc.
#     #exit(0) #removed exit so all files are processed.

# exit(ret_code)
