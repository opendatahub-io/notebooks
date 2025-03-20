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

REPO_ROOT=$(git rev-parse --show-toplevel)
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
        # use `--no-tags` for skopeo once available in newer version
        digest=$(skopeo inspect --retry-times 3 "docker://${registry}:${latest_tag}" | jq .Digest | tr -d '"')
        output="${registry}@${digest}"
        echo "NEW: ${output}"
        sed -i "s|${image}=.*|${image}=${output}|" "${PARAMS_ENV_PATH}"
    done

    update_commits "$REPO_ROOT" "$HASH"

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

        digest=$(skopeo inspect --retry-times 3 "docker://${registry}:${latest_tag}" | jq .Digest | tr -d '"')
        output="${registry}@${digest}"
        echo "NEW: ${output}"
        sed -i "s|${image}=.*|${image}=${output}|" "${PARAMS_ENV_PATH}"
        i=$((i+1))
    done

    update_commits "$REPO_ROOT" "$HASH"

else
    echo "This script runs exclusively for the 'opendatahub-io' and 'red-hat-datascience' organizations, as it verifies/updates their corresponding quay.io registries."
    exit 1

fi

