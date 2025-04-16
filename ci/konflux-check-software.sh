#!/bin/bash
#
# TODO - description, prereq and usage etc...

download_sbom_with_retry() {
    local status=-1
    local max_try=5
    local wait_sec=2

    local platform_arg="${1}"
    local image_url="${2}"
    local sbom="${3}"

    for run in $(seq 1 ${max_try}); do
        status=0
        ./cosign download sbom ${platform_arg} ${image_url} 2>>err 1>>"${sbom}"
        status=$?
        if [ "$status" -eq 0 ]; then
            break
        fi
        sleep ${wait_sec}
    done
    if [ "${status}" -ne 0 ]; then
        echo "Failed to get SBOM after ${max_try} tries" >&2
        cat err >&2
    fi
}

# Find all YAML files in the specified directory and select the one that matches the expected metadata.name value.
select_manifest() {
    local yaml_directory="${1}"
    local expected_name="${2}"

    find "${yaml_directory}" -type f -name "*imagestream.yaml" -o -name "*.yml" -print0 | while IFS= read -r -d $'\0' file; do
        # Check if the metadata.name field exists and contains the specified name element
        if yq '.metadata.name' "${file}" | grep -q "^${expected_name}-notebook$"; then
            echo "${file}"
            return
        fi
    done
}


process_the_software_versions() {
    local manifest_file="${1}"
    local sbom="${2}"

    for

    jq -r '.packages[] | select(.name == "boto3") | .versionInfo' ./sbom.json

    echo "Processing file: ${file}"
    echo "---"

    # Iterate over the selected fields and extract the data
    for field in "${selected_fields[@]}"; do
    echo "  $field:"
    if value=$(extract_yaml_data "$file" "$field"); then
        echo "    $value"
    else
        echo "    (Not found or error)"
    fi
    done
    echo "---"
}

RAW_OUTPUT=$(skopeo inspect --no-tags --raw "docker://${IMAGE_URL}")
if [ "$(jq 'has("manifests")' <<< "${RAW_OUTPUT}")" == "true" ] ; then
    # Multi arch
    OS=$(jq -r '.manifests[].platform.os' <<< ${RAW_OUTPUT})
    ARCH=$(jq -r '.manifests[].platform.architecture' <<< ${RAW_OUTPUT})
    if test "${ARCH}" = "amd64"; then
        ARCH="x86-64"
    fi
    PLATFORM="${OS}-${ARCH}"
else
    PLATFORM=""
fi

RAW_OUTPUT_CONFIG=$(skopeo inspect --no-tags --config --raw "docker://${IMAGE_URL}")

# LABEL name="odh-notebook-jupyter-datascience-ubi9-python-3.11" \
LABEL_NAME=$(jq -r '.container_config.Labels.name' <<< ${RAW_OUTPUT_CONFIG})
echo "Image label name: ${LABEL_NAME}"
# Filter the required value from the image label name
LABEL=$(echo ${LABEL_NAME} | sed 's/odh-notebook-\(.*\)-ubi9.*/\1/')


MANIFEST_TO_PROCESS=$(select_manifest "manifests" "${LABEL}")

SBOM_FILE="./sbom.json"

if [ -z "${PLATFORM}" ] ; then
    # single arch image
    # download_sbom_with_retry "" "${IMAGE_URL}"
    download_sbom_with_retry "" "${IMAGE_URL}-${PLATFORM}" "${SBOM_FILE}"
else
    # download_sbom_with_retry " --platform=${PLATFORM} " "${IMAGE_URL}"-
    download_sbom_with_retry "" "${IMAGE_URL}-${PLATFORM}" "${SBOM_FILE}"
fi



process_the_software_versions "${MANIFEST_TO_PROCESS}" "${SBOM_FILE}"
