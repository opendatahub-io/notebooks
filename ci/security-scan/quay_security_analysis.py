import fileinput
import os
import re
import subprocess
from collections import Counter
from datetime import date

import requests

branch_dictionary = {}

commit_id_path = "ci/security-scan/weekly_commit_ids.env"

IMAGES_MAIN = [
    "odh-minimal-notebook-image-main",
    "odh-runtime-minimal-notebook-image-main",
    "odh-runtime-data-science-notebook-image-main",
    "odh-minimal-gpu-notebook-image-main",
    "odh-pytorch-gpu-notebook-image-main",
    "odh-generic-data-science-notebook-image-main",
    "odh-tensorflow-gpu-notebook-image-main",
    "odh-trustyai-notebook-image-main",
    "odh-codeserver-notebook-image-main",
    "odh-rstudio-notebook-image-main",
    "odh-rstudio-gpu-notebook-image-main",
]

IMAGES = [
    "odh-minimal-notebook-image-n",
    "odh-runtime-minimal-notebook-image-n",
    "odh-runtime-data-science-notebook-image-n",
    "odh-minimal-gpu-notebook-image-n",
    "odh-pytorch-gpu-notebook-image-n",
    "odh-runtime-pytorch-notebook-image-n",
    "odh-generic-data-science-notebook-image-n",
    "odh-tensorflow-gpu-notebook-image-n",
    "odh-runtime-tensorflow-notebook-image-n",
    "odh-trustyai-notebook-image-n",
    "odh-codeserver-notebook-image-n",
    "odh-rstudio-notebook-image-n",
    "odh-rstudio-gpu-notebook-image-n",
]

IMAGES_N_1 = [
    "odh-minimal-notebook-image-n-1",
    "odh-runtime-minimal-notebook-image-n-1",
    "odh-minimal-gpu-notebook-image-n-1",
    "odh-pytorch-gpu-notebook-image-n-1",
    "odh-runtime-pytorch-notebook-image-n-1",
    "odh-runtime-data-science-notebook-image-n-1",
    "odh-generic-data-science-notebook-image-n-1",
    "odh-tensorflow-gpu-notebook-image-n-1",
    "odh-runtime-tensorflow-notebook-image-n-1",
    "odh-trustyai-notebook-image-n-1",
    "odh-codeserver-notebook-image-n-1",
    "odh-rstudio-notebook-image-n-1",
    "odh-rstudio-gpu-notebook-image-n-1",
]


def generate_markdown_table(branch_dictionary):
    markdown_data = ""
    for key, value in branch_dictionary.items():
        markdown_data += f"| [{key}](https://quay.io/repository/opendatahub/workbench-images/manifest/{value['sha']}?tab=vulnerabilities) |"
        for severity in ["Medium", "Low", "Unknown", "High", "Critical"]:
            count = value.get(severity, 0)  # Get count for the severity, default to 0 if not present
            markdown_data += f" {count} |"
        markdown_data += "\n"
    return markdown_data


def process_image(image, commit_id_path, RELEASE_VERSION_N, HASH_N):
    with open(commit_id_path, "r") as params_file:
        img_line = next(line for line in params_file if re.search(f"{image}=", line))
        img = img_line.split("=")[1].strip()

    registry = img.split("@")[0]

    src_tag_cmd = (
        f'skopeo inspect docker://{img} | jq \'.Env[] | select(startswith("OPENSHIFT_BUILD_NAME=")) | split("=")[1]\''
    )
    src_tag = subprocess.check_output(src_tag_cmd, shell=True, text=True).strip().strip('"').replace("-amd64", "")

    regex = ""

    if RELEASE_VERSION_N == "":
        regex = f"^{src_tag}-(\\d+-)?{HASH_N}$"
    else:
        regex = f"^{src_tag}-{RELEASE_VERSION_N}-\\d+-{HASH_N}$"

    latest_tag_cmd = f"skopeo inspect docker://{img} | jq -r --arg regex \"{regex}\" '.RepoTags | map(select(. | test($regex))) | .[0]'"
    latest_tag = subprocess.check_output(latest_tag_cmd, shell=True, text=True).strip()

    digest_cmd = f"skopeo inspect docker://{registry}:{latest_tag} | jq .Digest | tr -d '\"'"
    digest = subprocess.check_output(digest_cmd, shell=True, text=True).strip()

    if digest is None or digest == "":
        return

    output = f"{registry}@{digest}"

    sha_ = output.split(":")[1]

    url = f"https://quay.io/api/v1/repository/opendatahub/workbench-images/manifest/sha256:{sha_}/security"

    response = requests.get(url)
    data = response.json()

    vulnerabilities = []

    for feature in data["data"]["Layer"]["Features"]:
        if len(feature["Vulnerabilities"]) > 0:
            for vulnerability in feature["Vulnerabilities"]:
                vulnerabilities.append(vulnerability)

    severity_levels = [entry.get("Severity", "Unknown") for entry in vulnerabilities]
    severity_counts = Counter(severity_levels)

    branch_dictionary[latest_tag] = {}
    branch_dictionary[latest_tag]["sha"] = digest

    for severity, count in severity_counts.items():
        branch_dictionary[latest_tag][severity] = count

    for line in fileinput.input(commit_id_path, inplace=True):
        if line.startswith(f"{image}="):
            line = f"{image}={output}\n"
        print(line, end="")


today = date.today()
d2 = today.strftime("%B %d, %Y")

LATEST_MAIN_COMMIT = os.environ["LATEST_MAIN_COMMIT"]

for i, image in enumerate(IMAGES_MAIN):
    process_image(image, commit_id_path, "", LATEST_MAIN_COMMIT)

branch_main_data = generate_markdown_table(branch_dictionary)
branch_dictionary = {}

RELEASE_VERSION_N = os.environ["RELEASE_VERSION_N"]
HASH_N = os.environ["HASH_N"]

for i, image in enumerate(IMAGES):
    process_image(image, commit_id_path, RELEASE_VERSION_N, HASH_N)

branch_n_data = generate_markdown_table(branch_dictionary)
branch_dictionary = {}

RELEASE_VERSION_N_1 = os.environ["RELEASE_VERSION_N_1"]
HASH_N_1 = os.environ["HASH_N_1"]

for i, image in enumerate(IMAGES_N_1):
    process_image(image, commit_id_path, RELEASE_VERSION_N_1, HASH_N_1)

branch_n_1_data = generate_markdown_table(branch_dictionary)

markdown_content = """# Security Scan Results

Date: {todays_date}

# Branch main

| Image Name | Medium | Low | Unknown | High | Critical |
|------------|-------|-----|---------|------|------|
{branch_main}

# Branch N

| Image Name | Medium | Low | Unknown | High | Critical |
|------------|-------|-----|---------|------|------|
{branch_n}

# Branch N - 1

| Image Name | Medium | Low | Unknown | High | Critical |
|------------|-------|-----|---------|------|------|
{branch_n_1}
"""

final_markdown = markdown_content.format(
    branch_n=branch_n_data, todays_date=d2, branch_n_1=branch_n_1_data, branch_main=branch_main_data
)

# Writing to the markdown file
with open("ci/security-scan/security_scan_results.md", "w") as markdown_file:
    markdown_file.write(final_markdown)
