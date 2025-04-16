#!/bin/bash

USER_HASH=$1
REPO_OWNER=$2
BRANCH=$3
REPO_NAME=$4

REPO_ROOT=$(git rev-parse --show-toplevel)
# Declare and initialize the image skipping log file (This does not commit)
export SKIPPED_LOG="$REPO_ROOT/skipped-images.txt"

init_skipped_log() {
    mkdir -p "$(dirname "$SKIPPED_LOG")"
    touch "$SKIPPED_LOG"
}

log_skipped_image() {
    local image_name="$1"
    echo ":x: — No matching sha for $image_name" >> "$SKIPPED_LOG"
}

# Fetch the latest commit hash (or use the user-provided one)
fetch_latest_hash() {
    local org="$1"
    local api_url="https://api.github.com/repos/$org/$REPO_NAME"

    if [[ -n "$USER_HASH" ]]; then
        HASH=$USER_HASH
        echo "Using user-provided HASH: $HASH"
    else
        PAYLOAD=$(curl --silent -H 'Accept: application/vnd.github.v4.raw' "$api_url/commits?sha=$BRANCH&per_page=1")
        HASH=$(echo "$PAYLOAD" | jq -r '.[0].sha' | cut -c1-7)
        echo "Extracted HASH: $HASH"
    fi
}

# Updates the commits in commit.env
update_commits() {
    local REPO_ROOT="$1"
    local HASH="$2"
    local COMMIT_ENV_PATH="$REPO_ROOT/manifests/base/commit.env"

    # Get the complete list of commits N-version to update
    local COMMITS
    COMMITS=$(grep "\-n=" "$COMMIT_ENV_PATH" | cut -d "=" -f 1)

    for val in $COMMITS; do
        echo "Updating commit '${val}' to $HASH"
        sed -i "s|${val}=.*|${val}=${HASH}|" "$COMMIT_ENV_PATH"
    done
}

# Function to process runtime images
update_runtime_images() {
    MANIFEST_DIR="$REPO_ROOT/manifests/base"
    # Find matching files
    files=$(find "$MANIFEST_DIR" -type f -name "runtime-*.yaml")
    for file in $files; do
        echo "PROCESSING: $file"

        # Extract values
        img=$(yq e '.spec.tags[].annotations."opendatahub.io/runtime-image-metadata" | fromjson | .[].metadata.image_name' "$file" 2>/dev/null)
        name=$(yq e '.spec.tags[].name' "$file" 2>/dev/null)
        ubi=$(yq e '.metadata.annotations."opendatahub.io/runtime-image-name"' "$file" 2>/dev/null | grep -oE 'UBI[0-9]+' | tr '[:upper:]' '[:lower:]')
        py_version=$(yq e '.metadata.annotations."opendatahub.io/runtime-image-name"' "$file" 2>/dev/null | grep -oE 'Python [0-9]+\.[0-9]+' | sed 's/ /-/g' | tr '[:upper:]' '[:lower:]')
        registry=$(echo "$img" | cut -d '@' -f1)

        # Handling specific cases
        if [[ $name == tensorflow || $name == pytorch ]]; then
            name="cuda-$name"
        elif [[ $name == ubi ]]; then
            name="minimal-$name"
        elif [[ $name == rocm-pytorch ]]; then
            name="${name/rocm-pytorch/rocm-runtime-pytorch}"
        elif [[ $name == rocm-tensorflow ]]; then
            name="${name/rocm-tensorflow/rocm-runtime-tensorflow}"
        fi

        # Construct regex pattern
        prefix="runtime-"
        [[ $name == rocm-* ]] && prefix=""
        regex="^${prefix}$name-$ubi-$py_version-[0-9]{8}-$HASH$"

        latest_tag=$(skopeo inspect --retry-times 3 "docker://$img" | jq -r --arg regex "$regex" '.RepoTags | map(select(. | test($regex))) | .[0]')
        echo "CHECKING: ${latest_tag}"

        # Check for latest_tag validity (maybe the new image is not yet built)
        if [[ -z "$latest_tag" || "$latest_tag" == "null" ]]; then
            echo "No matching tag found on registry for $file. Skipping."
            # Get relative path from REPO_ROOT/ci to the file
            relative_path=$(echo "$file" | sed "s|$REPO_ROOT/||")
            # calls log_skipped_image funtion from image-skipping-logger.sh script
            log_skipped_image "../$relative_path"
            continue
        fi

        # Extract the digest sha from the latest tag
        digest=$(skopeo inspect --retry-times 3 "docker://$registry:$latest_tag" | jq .Digest | tr -d '"')

        # Check for digest validity
        if [[ -z "$digest" || "$digest" == "null" ]]; then
            echo "Failed to get digest for $latest_tag. Skipping."
            # Get relative path from REPO_ROOT/ci to the file
            relative_path=$(echo "$file" | sed "s|$REPO_ROOT/||")
            # calls log_skipped_image funtion from image-skipping-logger.sh script
            log_skipped_image "../$relative_path"
            continue
        fi

        output="${registry}@${digest}"
        echo "NEW: ${output}"

        # Updates the ImageStream with the new SHAs
        yq e -i '(.spec.tags[] | .from.name) = "'"$output"'"' "$file"
        sed -i "s|\(\"image_name\": \"\)[^\"]*|\1${output}|" "$file"

    done
}

init_skipped_log

PARAMS_ENV_PATH="$REPO_ROOT/manifests/base/params.env"
# In case the digest updater function is triggered upstream.
if [[ "$REPO_OWNER" == "opendatahub-io" ]]; then

    echo "This is opendatahub-io org"
    fetch_latest_hash "$REPO_OWNER"
    # Get the complete list of images to update
    IMAGES=$(grep "\-n=" "${PARAMS_ENV_PATH}" | cut -d "=" -f 1)
    for image in ${IMAGES}; do

        echo "CHECKING: '${image}'"
        img=$(grep -E "${image}=" "${PARAMS_ENV_PATH}" | cut -d '=' -f2)
        registry=$(echo "${img}" | cut -d '@' -f1)

        skopeo_metadata=$(skopeo inspect --retry-times 3 "docker://${img}")
        src_tag=$(echo "${skopeo_metadata}" | jq '.Env[] | select(startswith("OPENSHIFT_BUILD_NAME=")) | split("=")[1]' | tr -d '"' | sed 's/-amd64$//')
        # Handling PyTorch to match with regex pattern
        if [[ $src_tag == jupyter-pytorch* ]]; then
           src_tag="cuda-$src_tag"
        fi
        # This should match like for ex: jupyter-minimal-ubi9-python-3.11-20250310-60b6ecc tag name as is on quay.io registry
        regex="^$src_tag-[0-9]{8}-$HASH$"
        latest_tag=$(echo "${skopeo_metadata}" | jq -r --arg regex "$regex" '.RepoTags | map(select(. | test($regex))) | .[0]')

        # Check for latest_tag validity (maybe the new image is not yet build)
        if [[ -z "$latest_tag" || "$latest_tag" == "null" ]]; then
            echo "No matching tag found on registry for $file. Skipping."
            # calls log_skipped_image to log missing updates
            log_skipped_image "$image"
            continue
        fi

        # use `--no-tags` for skopeo once available in newer version
        digest=$(skopeo inspect --retry-times 3 "docker://${registry}:${latest_tag}" | jq .Digest | tr -d '"')

        # Check for digest validity
        if [[ -z "$digest" || "$digest" == "null" ]]; then
            echo "Failed to get digest for $latest_tag. Skipping."
            log_skipped_image "$image"
            continue
        fi

        output="${registry}@${digest}"
        echo "NEW: ${output}"
        sed -i "s|${image}=.*|${image}=${output}|" "${PARAMS_ENV_PATH}"
    done

    update_commits "$REPO_ROOT" "$HASH"
    update_runtime_images

# In case the digest updater function is triggered downstream.
elif [[ "$REPO_OWNER" == "red-hat-data-services" ]]; then

    echo "This is red-hat-data-services org"
    fetch_latest_hash "$REPO_OWNER"
    # Get the complete list of images to update
    IMAGES=$(grep "\-n=" "${PARAMS_ENV_PATH}" | cut -d "=" -f 1)
    # The order of the regexes array should match with the params.env file
    REGEXES=("^v3-[0-9]{8}-$HASH$" \
              "^cuda-[a-z]+-minimal-[a-z0-9]+-[a-z]+-3.11-[0-9]{8}-$HASH$" \
              "^v3-[0-9]{8}-$HASH$" \
              "^v3-[0-9]{8}-$HASH$" \
              "^cuda-[a-z]+-tensorflow-[a-z0-9]+-[a-z]+-3.11-[0-9]{8}-$HASH$" \
              "^v3-[0-9]{8}-$HASH$" \
              "^codeserver-[a-z0-9]+-[a-z]+-3.11-[0-9]{8}-$HASH$" \
              "^rocm-[a-z]+-minimal-[a-z0-9]+-[a-z]+-3.11-[0-9]{8}-$HASH$" \
              "^rocm-[a-z]+-pytorch-[a-z0-9]+-[a-z]+-3.11-[0-9]{8}-$HASH$" \
              "^rocm-[a-z]+-tensorflow-[a-z0-9]+-[a-z]+-3.11-[0-9]{8}-$HASH$")
    i=0
    for image in ${IMAGES}; do
        echo "CHECKING: '${image}'"
        img=$(grep -E "${image}=" "${PARAMS_ENV_PATH}" | cut -d '=' -f2)
        registry=$(echo "${img}" | cut -d '@' -f1)

        regex=${REGEXES[$i]}
        skopeo_metadata=$(skopeo inspect --retry-times 3 "docker://${img}")
        latest_tag=$(echo "${skopeo_metadata}" | jq -r --arg regex "$regex" '.RepoTags | map(select(. | test($regex))) | .[0]')
        echo "CHECKING: '${latest_tag}'"

        # Check for latest_tag validity (maybe the new image is not yet built)
        if [[ -z "$latest_tag" || "$latest_tag" == "null" ]]; then
            echo "No matching tag found on registry for $file. Skipping."
            # calls log_skipped_image to log missing updates
            log_skipped_image "$image"
            continue
        fi

        digest=$(skopeo inspect --retry-times 3 "docker://${registry}:${latest_tag}" | jq .Digest | tr -d '"')

        # Check for digest validity
        if [[ -z "$digest" || "$digest" == "null" ]]; then
            echo "Failed to get digest for $latest_tag. Skipping."
            log_skipped_image "$image"
            continue
        fi

        output="${registry}@${digest}"
        echo "NEW: ${output}"
        sed -i "s|${image}=.*|${image}=${output}|" "${PARAMS_ENV_PATH}"
        i=$((i+1))
    done

    update_commits "$REPO_ROOT" "$HASH"
    update_runtime_images

else
    echo "This script runs exclusively for the 'opendatahub-io' and 'red-hat-datascience' organizations, as it verifies/updates their corresponding quay.io registries."
    exit 1
fi
