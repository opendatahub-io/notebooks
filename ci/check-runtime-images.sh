#!/bin/bash
#
# This script serves to check and validate the definitions for runtime images.
# It does just a brief check of the metadata defined in the json file:
#   1. checks that given `.metadata.image_name` is valid and can be accessed by skopeo tool
#   2. checks that tag in `.metadata.tags[0]` can be found in the output from skopeo tool
#
# THIS FILE DOESN'T CHECK THAT THE USED LINK TO IMAGE IS THE LATEST ONE AVAILABLE!
#
# This script uses `skopeo` and `jq` tools installed locally for retrieving
# information about the particular remote images.
#
# Local execution: ./ci/check-runtime-image.sh
#   Note: please execute from the root directory so that relative path matches
#
# In case of the PR on GitHub, this check is tied to GitHub actions automatically,
# see `.github/workflows` directory.

# ---------------------------- DEFINED FUNCTIONS ----------------------------- #

# Expected commit reference for the runtime images
EXPECTED_COMMIT_REF="2024b"

# Size change tresholds:
# Max percentual change
SIZE_PERCENTUAL_TRESHOLD=10
# Max absolute change in MB
SIZE_ABSOLUTE_TRESHOLD=100

function check_image_size() {
    local img_name="${1}"
    local actual_img_size="${2}"

    local expected_img_size

    case "${img_name}" in
        odh-notebook-runtime-datascience-ubi9-python-3.11)
            expected_img_size=866
            ;;
        odh-notebook-runtime-pytorch-ubi9-python-3.11)
            expected_img_size=3829
            ;;
        odh-notebook-runtime-rocm-pytorch-ubi9-python-3.11)
            expected_img_size=6477
            ;;
        odh-notebook-rocm-runtime-tensorflow-ubi9-python-3.11)
            expected_img_size=5660
            ;;
        odh-notebook-cuda-runtime-tensorflow-ubi9-python-3.11)
            expected_img_size=7992
            ;;
        odh-notebook-runtime-minimal-ubi9-python-3.11)
            expected_img_size=494
            ;;
        *)
            echo "Unimplemented image name: '${img_name}'"
            return 1
    esac

    # Check the size change constraints now
    if test -z "${expected_img_size}" || test "${expected_img_size}" -eq 0; then
        echo "Expected image size is undefined or empty, please check the pre-defined values!"
        return 1
    fi

    # 1. Percentual size change
    percent_change=$((100 * actual_img_size / expected_img_size - 100))
    abs_percent_change=${percent_change#-*}
    test ${abs_percent_change} -le ${SIZE_PERCENTUAL_TRESHOLD} || {
        echo "Image size changed by ${abs_percent_change}% (expected: ${expected_img_size} MB; actual: ${actual_img_size} MB; treshold: ${SIZE_PERCENTUAL_TRESHOLD}%)."
        return 1
    }
    # 2. Absolute size change
    size_difference=$((actual_img_size - expected_img_size))
    abs_size_difference=${size_difference#-*}
    test ${abs_size_difference} -le ${SIZE_ABSOLUTE_TRESHOLD} || {
        echo "Image size changed by ${abs_size_difference} MB (expected: ${expected_img_size} MB; actual: ${actual_img_size} MB; treshold: ${SIZE_ABSOLUTE_TRESHOLD} MB)."
        return 1
    }
}

function check_image() {
    local runtime_image_file="${1}"

    echo "---------------------------------------------"
    echo "Checking file: '${runtime_image_file}'"

    local img_tag
    local img_url
    local img_metadata_config
    local img_created
    local img_commit_ref
    local img_name

    img_tag=$(jq -r '.metadata.tags[0]' "${runtime_image_file}") || {
        echo "ERROR: Couldn't parse image tags metadata for '${runtime_image_file}' runtime image file!"
        return 1
    }
    echo "Image tag: '${img_tag}'"

    img_url=$(jq -r '.metadata.image_name' "${runtime_image_file}") || {
        echo "ERROR: Couldn't parse image URL metadata for '${runtime_image_file}' runtime image file!"
        return 1
    }
    echo "Image URL: '${img_url}'"

    img_metadata_config="$(skopeo inspect --config "docker://${img_url}")" || {
        echo "ERROR: Couldn't download '${img_url}' image config metadata with skopeo tool!"
        return 1
    }

    img_created=$(echo "${img_metadata_config}" | jq --raw-output '.created') ||  {
        echo "Couldn't parse '.created' from image metadata!"
        return 1
    }
    echo "Image created: '${img_created}'"

    img_commit_ref=$(echo "${img_metadata_config}" | jq --raw-output '.config.Labels."io.openshift.build.commit.ref"') ||  {
        echo "Couldn't parse '.Labels."io.openshift.build.commit.ref"' from image metadata!"
        return 1
    }
    echo "Image commit ref: '${img_commit_ref}'"

    img_name=$(echo "${img_metadata_config}" | jq --raw-output '.config.Labels.name') ||  {
        echo "Couldn't parse '.Labels.name' from image metadata!"
        return 1
    }
    echo "Image name: '${img_name}'"

    local expected_string="runtime-${img_tag}-ubi"
    echo "Checking that '${expected_string}' is present in the image metadata"
    echo "${img_metadata_config}" | grep --quiet "${expected_string}" || {
        echo "ERROR: The string '${expected_string}' isn't present in the image metadata at all. Please check that the referenced image '${img_url}' is the correct one!"
        return 1
    }

    test "${EXPECTED_COMMIT_REF}" == "${img_commit_ref}" || {
        echo "ERROR: The image 'io.openshift.build.commit.ref' label is '${img_commit_ref}' but should be '${EXPECTED_COMMIT_REF}' instead!"
        return 1
    }

    local img_metadata
    local img_size
    local img_size_mb

    img_metadata="$(skopeo inspect --raw "docker://${img_url}")" || {
        echo "ERROR: Couldn't download '${img_url}' image metadata with skopeo tool!"
        return 1
    }
    # Here we get the image size as a compressed image. This differs to what we gather in
    # 'tests/containers/base_image_test.py#test_image_size_change' where we check against the extracted image size.
    # There is no actual reason to compare these different sizes except that in this case we want to do check the
    # image remotely, whereas in the othe test, we have the image present locally on the machine.
    img_size=$(echo "${img_metadata}" | jq '[ .layers[].size ] | add') ||  {
        echo "Couldn't count image size from image metadata!"
        return 1
    }
    img_size_mb=$((img_size / 1024 / 1024)) ||  {
        echo "Couldn't count image size from image metadata!"
        return 1
    }
    echo "Image size: ${img_size_mb} MB"

    check_image_size "${img_name}" "${img_size_mb}" || return 1
}

function main() {
    ret_code=0

    # If name of the directory isn't good enough, maybe we can improve this to search for the: `"schema_name": "runtime-image"` string.
    runtime_image_files=$(find . -name "*.json" | grep "runtime-images" | sort --unique)

    IFS=$'\n'
    for file in ${runtime_image_files}; do
        check_image "${file}" || {
            echo "ERROR: Check for '${file}' failed!"
            ret_code=1
        }
    done

    echo "---------------------------------------------"
    echo ""
    if test "${ret_code}" -eq 0; then
        echo "Validation of runtime images definitions was successful! Congrats :)"
    else
        echo "ERROR: Some of the runtime image definitions aren't valid, please check above!"
    fi

    return "${ret_code}"
}

# ------------------------------ MAIN SCRIPT --------------------------------- #

main

exit "${?}"
