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

function check_image() {
    local runtime_image_file="${1}"

    echo "---------------------------------------------"
    echo "Checking file: '${runtime_image_file}'"

    local img_tag
    local img_url
    local img_metadata
    local img_created

    img_tag=$(jq -r '.metadata.tags[0]' "${runtime_image_file}") || {
        echo "ERROR: Couldn't parse image tags metadata for '${runtime_image_file}' runtime image file!"
        return 1
    }
    img_url=$(jq -r '.metadata.image_name' "${runtime_image_file}") || {
        echo "ERROR: Couldn't parse image URL metadata for '${runtime_image_file}' runtime image file!"
        return 1
    }

    img_metadata="$(skopeo inspect --config "docker://${img_url}")" || {
        echo "ERROR: Couldn't download '${img_url}' image metadata with skopeo tool!"
        return 1
    }

    img_created=$(echo "${img_metadata}" | jq --raw-output '.created') ||  {
        echo "Couldn't parse '.created' from image metadata!"
        return 1
    }

    local expected_string="runtime-${img_tag}-ubi"
    echo "Checking that '${expected_string}' is present in the image metadata"
    echo "${img_metadata}" | grep --quiet "${expected_string}" || {
        echo "ERROR: The string '${expected_string}' isn't present in the image metadata at all. Please check that the referenced image '${img_url}' is the correct one!"
        return 1
    }

    echo "Image created: '${img_created}'"

    # TODO: we shall extend this check to check also Label "io.openshift.build.commit.ref" value (e.g. '2024a') or something similar
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
