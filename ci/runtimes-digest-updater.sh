#!/bin/bash

TAG_VERSION=$1
USER_HASH=$2

REPO_OWNER="opendatahub-io"
REPO_NAME="notebooks"
GITHUB_API_URL="https://api.github.com/repos/$REPO_OWNER/$REPO_NAME"

if [[ -n "$USER_HASH" ]]; then
  HASH=$USER_HASH
  echo "Using user-provided HASH: $HASH"
else
  PAYLOAD=$(curl --silent -H 'Accept: application/vnd.github.v4.raw' "$GITHUB_API_URL/commits?sha=$TAG_VERSION&per_page=1")
  HASH=$(echo "$PAYLOAD" | jq -r '.[0].sha' | cut -c1-7)
  echo "Extracted HASH: $HASH"
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
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
  [[ $name == tensorflow* ]] && name="cuda-$name"

  if [[ $TAG_VERSION == main ]]; then
    # This should match with the runtime-image tag name as is on quay.io registry
    regex="^runtime-$name-$ubi-$py_version-[0-9]{8}-$HASH$"
  else
    # This should match with the runtime-image tag name as is on quay.io registry
    regex="^runtime-$name-$ubi-$py_version-$TAG_VERSION-[0-9]{8}-$HASH$"
  fi

  latest_tag=$(skopeo inspect --retry-times 3 "docker://$img" | jq -r --arg regex "$regex" '.RepoTags | map(select(. | test($regex))) | .[0]')
  echo "CHECKING: ${latest_tag}"

  if [[ -z "$latest_tag" || "$latest_tag" == "null" ]]; then
    echo "No matching tag found on registry for $file. Skipping."
    continue
  fi

  # Extract the digest sha from the latest tag
  digest=$(skopeo inspect --retry-times 3 "docker://$registry:$latest_tag" | jq .Digest | tr -d '"')
  output="${registry}@${digest}"
  echo "NEW: ${output}"

  # Updates the ImageStream with the new SHAs
  yq e -i '(.spec.tags[] | .from.name) = "'"$output"'"' "$file"
  sed -i "s|\(\"image_name\": \"\)[^\"]*|\1${output}|" "$file"

done
