#!/bin/bash
#
# This script serves to compare two docker images using skopeo tool. This gives
# a brief information regarding the following image differences:
#   - size
#   - architecture
#   - operating system
#   - config
#     - default user
#     - exposed ports
#     - environment variables
#     - entrypoint
#     - working directory
#     - labels
#   - Python packages
#   - RPM packages
#
# It uses the skopeo TODO downloads images locally...
#
# Local execution: ./ci/compare-images.sh <image-1> <image-2>
#   Note: <image-*> is in the format <repository@sha256:SHA>
#
# Example usage:
#    ./ci/compare-images.sh quay.io/opendatahub/workbench-images@sha256:e92bf20e127e545bdf56887903dc72ad227082b8bc23f45ff4f0fc67e6430318 ghcr.io/jiridanek/notebooks/workbench-images:base-ubi9-python-3.9-jd_ubi_base_adedd4a943977ecdcb67bc6eb9eda572d10c3ddc

shopt -s globstar


function gather_metadata() {
    local image="${1}"
    local tmp_dir="${2}"

    local ret_code=0

    echo "Gathering the metadata for the image: '${image}'"

    local image_sha
    image_sha=$(echo "${image}" | cut -d ':' -f2)
    echo "Image SHA: '${image_sha}'"

    # Get image size
    skopeo inspect --raw "docker://${image}" | jq '[ .layers[].size ] | add' > "${tmp_dir}/${image_sha}-size.txt"

    # Get image metadata
    skopeo inspect --config "docker://${image}" | jq -r '.architecture,.os,.config' > "${tmp_dir}/${image_sha}-metadata.txt"

    # If we don't want to download the image, then we may consider to utilize the quay.io info:
    # e.g.: https://quay.io/repository/opendatahub/workbench-images/manifest/sha256:f5a2c0666b5b03d68e6f9f2317b67f9bc5c3f4bd469bb7073dd144a33892f63a?tab=packages
    # Disadvantage is that it takes some time this info is available on the quay


    # Get image Python packages list
    podman run --entrypoint /usr/bin/pip --rm -it "${image}" list > "${tmp_dir}/${image_sha}-global-pip.txt"
    podman run --entrypoint /opt/app-root/bin/pip --rm -it "${image}" list > "${tmp_dir}/${image_sha}-local-pip.txt"

    # Inspiration how to get python package installation size:
    # pip list --format=name | while read package; do
    #     location=$(pip show "$package" | grep '^Location:' | head -n 1 | awk '{print $2}')
    #     package_base=$(echo "$package" | sed 's/-/_/g')
    #     package_dir=$(find "$location" -maxdepth 1 -name "$package" -o -name "$package-*" -o -name "$package_base" -o -name "$package_base-*" 2>/dev/null | head -n 1)
    #     if [ -n "$package_dir" ]; then
    #         du -sh "$package_dir" | awk '{print $1 "\t" $2}'
    #     else
    #         echo "N/A\t$package"
    #     fi
    # done | sort -hr

    # Get image RPM packages list
    podman run --entrypoint /usr/bin/rpm --rm -it "${image}" "-qa" | sort > "${tmp_dir}/${image_sha}-rpms.txt"
    # And now again but with the package size and sort it from the bigger one
    podman run --entrypoint /usr/bin/rpm --rm -it "${image}" "-qa" "--queryformat" "%10{SIZE} %{NAME}\\n" | sort -k1,1nr > "${tmp_dir}/${image_sha}-rpms-size.txt"
    # TODO - in the future, I can maybe run the rpm with appropriate format and have all the data in one file. Then I can process just selective diff on it, something like:
    # diff <(cut -c 1-10,20-30,40-50 file1.txt) <(cut -c 1-10,20-30,40-50 file2.txt)
    # or
    # diff <(awk '{print $1, $3, $5}' file1.txt) <(awk '{print $1, $3, $5}' file2.txt)

    echo "Metadata for image '${image}' gathered."
}

function compare_metadata() {
    local tmp_dir="${1}"

    echo "Let's compare the image metadata now:"

    diff -y "${tmp_dir}"/*-size.txt
    diff -y "${tmp_dir}"/*-metadata.txt
    diff -y "${tmp_dir}"/*-global-pip.txt
    diff -y "${tmp_dir}"/*-local-pip.txt
    diff -y "${tmp_dir}"/*-rpms.txt
    diff -y "${tmp_dir}"/*-rpms-size.txt
}

function print_results() {
    echo "Print results TODO"
}

# ------------------------------ MAIN SCRIPT --------------------------------- #

function main() {
    local image_1="${1}"
    local image_2="${2}"

    local ret_code=0

    if test $# -ne 2; then
        echo "Error: please provide two images for comparison!"
        return 1
    fi

    # Create a temporary directory for the gathered metadata
    local tmp_dir=""
    tmp_dir=$(mktemp -d /tmp/compare-images.XXXXX)

    # Gather the metadata for each image
    gather_metadata "${1}" "${tmp_dir}"
    gather_metadata "${2}" "${tmp_dir}"

    # Compare the metadata and prepare results
    compare_metadata "${tmp_dir}"

    # Print results
    print_results

    return "${ret_code}"
}

main "${@}"
exit $?
