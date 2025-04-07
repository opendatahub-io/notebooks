#!/bin/bash
#
# TODO - description, prereq and usage etc...

download_sbom_with_retry() {
    local status=-1
    local max_try=5
    local wait_sec=2

    local platform_arg="${1}"
    local image_url="${2}"

    for run in $(seq 1 ${max_try}); do
    status=0
    ./cosign download sbom ${platform_arg} ${image_url} 2>>err
    status=$?
    if [ "$status" -eq 0 ]; then
        break
    fi
    sleep $wait_sec
    done
    if [ "$status" -ne 0 ]; then
    echo "Failed to get SBOM after ${max_try} tries" >&2
    cat err >&2
    fi
}

RAW_OUTPUT=$(skopeo inspect --no-tags --raw "docker://${IMAGE_URL}")
if [ "$(jq 'has("manifests")' <<< "$RAW_OUTPUT")" == "true" ] ; then
    # Multi arch
    OS=$(jq -r '.manifests[].platform.os' <<< $RAW_OUTPUT)
    ARCH=$(jq -r '.manifests[].platform.architecture' <<< $RAW_OUTPUT)
    if test "${ARCH}" = "amd64"; then
        ARCH="x86-64"
    fi
    PLATFORM="${OS}-${ARCH}"
else
    PLATFORM=""
fi

if [ -z "${PLATFORM}" ] ; then
    # single arch image
    # download_sbom_with_retry "" "${IMAGE_URL}"
    download_sbom_with_retry "" "${IMAGE_URL}-${PLATFORM}"
else
    # download_sbom_with_retry " --platform=${PLATFORM} " "${IMAGE_URL}"-
    download_sbom_with_retry "" "${IMAGE_URL}-${PLATFORM}"
fi
