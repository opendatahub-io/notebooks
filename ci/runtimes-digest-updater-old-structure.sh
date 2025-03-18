#!/bin/bash

USER_HASH=$1
REPO_OWNER=$2
BRANCH=$3
REPO_NAME=$4

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

# Function to process runtime images
update_runtime_images() {
    find . -name runtime-images -type d -exec find {} -type f -print \; | grep python-3.11 | while read -r path; do
        echo "Processing the '${path}' file."

        img=$(jq -r '.metadata.image_name' "${path}")
        name=$(echo "$path" | sed 's#.*runtime-images/\(.*\)-py.*#\1#')
        py_version=$(echo "$path" | grep -o 'python-[0-9]\.[0-9]*')
        registry=$(echo "$img" | cut -d '@' -f1)

        # Handling specific name cases
        if [[ $name == tensorflow* || $name == pytorch* ]]; then
            name="cuda-$name"
        elif [[ $name == ubi* ]]; then
            name="minimal-$name"
        elif [[ $name == rocm-pytorch* ]]; then
            name="${name/rocm-pytorch/rocm-runtime-pytorch}"
        elif [[ $name == rocm-tensorflow* ]]; then
            name="${name/rocm-tensorflow/rocm-runtime-tensorflow}"
        fi

        # Construct regex pattern
        prefix="runtime-"
        [[ $name == rocm-* ]] && prefix=""
        regex="^${prefix}${name}-${py_version}-[0-9]{8}-$HASH$"

        latest_tag=$(skopeo inspect --retry-times 3 "docker://$img" | jq -r --arg regex "$regex" '.RepoTags | map(select(. | test($regex))) | .[0]')
        echo "CHECKING: ${latest_tag}"

        if [[ -z "$latest_tag" || "$latest_tag" == "null" ]]; then
            echo "No matching tag found on registry for $path. Skipping."
            continue
        fi

        digest=$(skopeo inspect --retry-times 3 "docker://$registry:$latest_tag" | jq .Digest | tr -d '"')
        output="${registry}@${digest}"
        echo "NEW: ${output}"

        jq --arg output "$output" '.metadata.image_name = $output' "$path" > "$path.tmp" && mv "$path.tmp" "$path"
    done
}

if [[ "$REPO_OWNER" == "opendatahub-io" ]]; then
    echo "This is opendatahub-io org"
    fetch_latest_hash "$REPO_OWNER"
    update_runtime_images

elif [[ "$REPO_OWNER" == "red-hat-data-services" ]]; then
    echo "This is red-hat-data-services org"
    fetch_latest_hash "$REPO_OWNER"
    update_runtime_images

else
    echo "This script runs exclusively for the 'opendatahub-io' and 'red-hat-datascience' organizations, as it verifies/updates their corresponding quay.io registries."
    exit 1

fi

