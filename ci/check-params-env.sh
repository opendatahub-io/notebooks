#!/bin/bash
#
# This script serves to check and validate the `params.env` file that contains
# definitions of the notebook images that are supposed to be used in the resulting
# release.
#
# It is verified that particular image link exists and is a proper type for the
# assigned variable name. Structure of the `params.env` file is also checked.
#
# THIS FILE DOESN'T CHECK THAT THE USED LINK TO IMAGE IS THE LATEST ONE AVAILABLE!
#
# This script uses `skopeo` and `jq` tools installed locally for retrieving
# information about the particular remote images.
#
# Local execution: ./ci/check-params-env.sh
#   Note: please execute from the root directory so that relative path matches
#
# In case of the PR on GitHub, this check is tied to GitHub actions automatically,
# see `.github/workflows` directory.

# ----------------------------- GLOBAL VARIABLES ----------------------------- #

COMMIT_ENV_PATH="manifests/base/commit.env"
PARAMS_ENV_PATH="manifests/base/params.env"

# This value needs to be updated everytime we deliberately change number of the
# images we want to have in the `params.env` file.
EXPECTED_NUM_RECORDS=45

# Size change tresholds:
# Max percentual change
SIZE_PERCENTUAL_TRESHOLD=10
# Max absolute change in MB
SIZE_ABSOLUTE_TRESHOLD=100

# ---------------------------- DEFINED FUNCTIONS ----------------------------- #

function check_variables_uniq() {
    local env_file_path="${1}"
    local allow_value_duplicity="${2:=false}"
    local ret_code=0

    echo "Checking that all variables in the file '${env_file_path}' are unique and expected"

    local content
    content=$(sed 's#\(.*\)=.*#\1#' "${env_file_path}" | sort)

    local num_records
    num_records=$(echo "${content}" | wc -l)

    local num_uniq_records
    num_uniq_records=$(echo "${content}" | uniq | wc -l)

    test "${num_records}" -eq "${num_uniq_records}" || {
        echo "Some of the variables in the file aren't unique!"
        ret_code=1
    }

    # ----
    if test "${allow_value_duplicity}" = "false"; then
        echo "Checking that all values assigned to variables in the file '${env_file_path}' are unique and expected"

        content=$(sed 's#.*=\(.*\)#\1#' "${env_file_path}" | sort)

        local num_values
        num_values=$(echo "${content}" | wc -l)

        local num_uniq_values
        num_uniq_values=$(echo "${content}" | uniq | wc -l)

        test "${num_values}" -eq "${num_uniq_values}" || {
            echo "Some of the values in the file aren't unique!"
            ret_code=1
        }
    fi

    # ----
    echo "Checking that there are expected number of records in the file '${env_file_path}'"

    test "${num_records}" -eq "${EXPECTED_NUM_RECORDS}" || {
        echo "Number of records in the file is incorrect - expected '${EXPECTED_NUM_RECORDS}' but got '${num_records}'!"
        ret_code=1
    }

    echo "---------------------------------------------"
    return "${ret_code}"
}

function check_image_variable_matches_name_and_commitref_and_size() {
    local image_variable="${1}"
    local image_name="${2}"
    local image_commitref="${3}"
    local openshift_build_name="${4}"
    local actual_img_size="${5}"

    local expected_name
    local expected_commitref
    local expected_build_name
    local expected_img_size

    case "${image_variable}" in
        odh-minimal-notebook-image-n)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="jupyter-minimal-ubi9-python-3.11-amd64"
            expected_img_size=528
            ;;
        odh-minimal-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="jupyter-minimal-ubi9-python-3.11-amd64"
            expected_img_size=528
            ;;
        odh-minimal-notebook-image-n-2)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="jupyter-minimal-ubi9-python-3.9-amd64"
            expected_img_size=489
            ;;
        odh-minimal-notebook-image-n-3)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="jupyter-minimal-ubi9-python-3.9-amd64"
            expected_img_size=486
            ;;
        odh-minimal-notebook-image-n-4)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="release-2023a"
            expected_build_name="jupyter-minimal-ubi9-python-3.9-amd64"
            expected_img_size=475
            ;;
        odh-minimal-notebook-image-n-5)
            expected_name="odh-notebook-jupyter-minimal-ubi8-python-3.8"
            expected_commitref="release-1.2"
            expected_build_name="jupyter-minimal-ubi8-python-3.8-amd64"
            expected_img_size=479
            ;;
        odh-minimal-gpu-notebook-image-n)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.11-amd64"
            expected_img_size=5157
            ;;
        odh-minimal-gpu-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.11-amd64"
            expected_img_size=5157
            ;;
        odh-minimal-gpu-notebook-image-n-2)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.9-amd64"
            expected_img_size=6026
            ;;
        odh-minimal-gpu-notebook-image-n-3)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.9-amd64"
            expected_img_size=5326
            ;;
        odh-minimal-gpu-notebook-image-n-4)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="release-2023a"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.9-amd64"
            expected_img_size=5038
            ;;
        odh-minimal-gpu-notebook-image-n-5)
            expected_name="odh-notebook-jupyter-minimal-ubi8-python-3.8"
            expected_commitref="release-1.2"
            expected_build_name="cuda-jupyter-minimal-ubi8-python-3.8-amd64"
            expected_img_size=5333
            ;;
        odh-pytorch-gpu-notebook-image-n)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="jupyter-pytorch-ubi9-python-3.11-amd64"
            expected_img_size=8571
            ;;
        odh-pytorch-gpu-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="jupyter-pytorch-ubi9-python-3.11-amd64"
            expected_img_size=8571
            ;;
        odh-pytorch-gpu-notebook-image-n-2)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="jupyter-pytorch-ubi9-python-3.9-amd64"
            expected_img_size=9354
            ;;
        odh-pytorch-gpu-notebook-image-n-3)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="jupyter-pytorch-ubi9-python-3.9-amd64"
            expected_img_size=8711
            ;;
        odh-pytorch-gpu-notebook-image-n-4)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.9"
            expected_commitref="release-2023a"
            expected_build_name="jupyter-pytorch-ubi9-python-3.9-amd64"
            expected_img_size=7130
            ;;
        odh-pytorch-gpu-notebook-image-n-5)
            expected_name="odh-notebook-cuda-jupyter-pytorch-ubi8-python-3.8"
            expected_commitref="release-1.2"
            expected_build_name="jupyter-pytorch-ubi8-python-3.8-amd64"
            expected_img_size=6592
            ;;
        odh-generic-data-science-notebook-image-n)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="jupyter-datascience-ubi9-python-3.11-amd64"
            expected_img_size=961
            ;;
        odh-generic-data-science-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="jupyter-datascience-ubi9-python-3.11-amd64"
            expected_img_size=961
            ;;
        odh-generic-data-science-notebook-image-n-2)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="jupyter-datascience-ubi9-python-3.9-amd64"
            expected_img_size=890
            ;;
        odh-generic-data-science-notebook-image-n-3)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="jupyter-datascience-ubi9-python-3.9-amd64"
            expected_img_size=883
            ;;
        odh-generic-data-science-notebook-image-n-4)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.9"
            expected_commitref="release-2023a"
            expected_build_name="jupyter-datascience-ubi9-python-3.9-amd64"
            expected_img_size=685
            ;;
        odh-generic-data-science-notebook-image-n-5)
            expected_name="odh-notebook-jupyter-datascience-ubi8-python-3.8"
            expected_commitref="release-1.2"
            expected_build_name="jupyter-datascience-ubi8-python-3.8-amd64"
            expected_img_size=865
            ;;
        odh-tensorflow-gpu-notebook-image-n)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.11-amd64"
            expected_img_size=8211
            ;;
        odh-tensorflow-gpu-notebook-image-n-1)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.11-amd64"
            expected_img_size=8211
            ;;
        odh-tensorflow-gpu-notebook-image-n-2)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.9-amd64"
            expected_img_size=6984
            ;;
        odh-tensorflow-gpu-notebook-image-n-3)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.9-amd64"
            expected_img_size=6301
            ;;
        odh-tensorflow-gpu-notebook-image-n-4)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.9"
            expected_commitref="release-2023a"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.9-amd64"
            expected_img_size=5927
            ;;
        odh-tensorflow-gpu-notebook-image-n-5)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi8-python-3.8"
            expected_commitref="release-1.2"
            expected_build_name="cuda-jupyter-tensorflow-ubi8-python-3.8-amd64"
            expected_img_size=6309
            ;;
        odh-trustyai-notebook-image-n)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="jupyter-trustyai-ubi9-python-3.11-amd64"
            expected_img_size=4197
            ;;
        odh-trustyai-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="jupyter-trustyai-ubi9-python-3.11-amd64"
            expected_img_size=4197
            ;;
        odh-trustyai-notebook-image-n-2)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="jupyter-trustyai-ubi9-python-3.9-amd64"
            expected_img_size=1123
            ;;
        odh-trustyai-notebook-image-n-3)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="jupyter-trustyai-ubi9-python-3.9-amd64"
            expected_img_size=1057
            ;;
        odh-trustyai-notebook-image-n-4)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.9"
            expected_commitref="release-2023a"
            expected_build_name="jupyter-trustyai-ubi9-python-3.9-amd64"
            expected_img_size=883
            ;;
        odh-codeserver-notebook-image-n)
            expected_name="odh-notebook-code-server-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="codeserver-ubi9-python-3.11-amd64"
            expected_img_size=893
            ;;
        odh-codeserver-notebook-image-n-1)
            expected_name="odh-notebook-code-server-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="codeserver-ubi9-python-3.11-amd64"
            expected_img_size=893
            ;;
        odh-codeserver-notebook-image-n-2)
            expected_name="odh-notebook-code-server-ubi9-python-3.9"
            expected_commitref="release-2024a"
            expected_build_name="codeserver-ubi9-python-3.9-amd64"
            expected_img_size=837
            ;;
        odh-codeserver-notebook-image-n-3)
            expected_name="odh-notebook-code-server-ubi9-python-3.9"
            expected_commitref="release-2023b"
            expected_build_name="codeserver-ubi9-python-3.9-amd64"
            expected_img_size=778
            ;;
        odh-rocm-minimal-notebook-image-n)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="rocm-jupyter-minimal-ubi9-python-3.11-amd64"
            expected_img_size=4830
            ;;
        odh-rocm-minimal-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="rocm-jupyter-minimal-ubi9-python-3.11-amd64"
            expected_img_size=4830
            ;;
        odh-rocm-pytorch-notebook-image-n)
            expected_name="odh-notebook-jupyter-rocm-pytorch-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="rocm-jupyter-pytorch-ubi9-python-3.11-amd64"
            expected_img_size=6571
            ;;
        odh-rocm-pytorch-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-rocm-pytorch-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="rocm-jupyter-pytorch-ubi9-python-3.11-amd64"
            expected_img_size=6571
            ;;
        odh-rocm-tensorflow-notebook-image-n)
            expected_name="odh-notebook-jupyter-rocm-tensorflow-ubi9-python-3.11"
            expected_commitref="main"
            expected_build_name="rocm-jupyter-tensorflow-ubi9-python-3.11-amd64"
            expected_img_size=5782
            ;;
        odh-rocm-tensorflow-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-rocm-tensorflow-ubi9-python-3.11"
            expected_commitref="release-2024b"
            expected_build_name="rocm-jupyter-tensorflow-ubi9-python-3.11-amd64"
            expected_img_size=5782
            ;;
        *)
            echo "Unimplemented variable name: '${image_variable}'"
            return 1
    esac

    test "${image_name}" = "${expected_name}" || {
        echo "Image URL points to an incorrect image: expected name '${expected_name}'; actual '${image_name}'"
        return 1
    }

    test "${image_commitref}" = "${expected_commitref}" || {
        echo "Image URL points to an incorrect image: expected commitref '${expected_commitref}'; actual '${image_commitref}'"
        return 1
    }

    test "${openshift_build_name}" = "${expected_build_name}" || {
        echo "Image URL points to an incorrect image: expected OPENSHIFT_BUILD_NAME '${expected_build_name}'; actual '${openshift_build_name}'"
        return 1
    }

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

function check_image_commit_id_matches_metadata() {
    local image_variable="${1}"
    local image_commit_id="${2}"

    local short_image_commit_id
    # We're interested only in the first 7 characters of the commit ID
    short_image_commit_id=${image_commit_id:0:7}

    local file_image_commit_id

    file_image_commit_id=$(sed 's#-commit##' "${COMMIT_ENV_PATH}" | grep "${image_variable}=" | cut --delimiter "=" --field 2)
    test -n "${file_image_commit_id}" || {
        echo "Couldn't retrieve commit id for image variable '${image_variable}' in '${COMMIT_ENV_PATH}'!"
        return 1
    }

    test "${short_image_commit_id}" = "${file_image_commit_id}" || {
        echo "Image commit IDs for image variable '${image_variable}' don't equal!"
        echo "Image commit ID gathered from image: '${short_image_commit_id}'"
        echo "Image commit ID in '${COMMIT_ENV_PATH}': '${file_image_commit_id}'"
        return 1
    }
}

function check_image() {
    local image_variable="${1}"
    local image_url="${2}"

    echo "Checking metadata for image '${image_variable}' with URL '${image_url}'"

    local image_metadata_config
    local image_name
    local image_commit_id
    local image_commitref
    local image_created

    image_metadata_config="$(skopeo inspect --config "docker://${image_url}")" || {
        echo "Couldn't download image config metadata with skopeo tool!"
        return 1
    }
    image_name=$(echo "${image_metadata_config}" | jq --raw-output '.config.Labels.name') ||  {
        echo "Couldn't parse '.config.Labels.name' from image metadata!"
        return 1
    }
    image_commit_id=$(echo "${image_metadata_config}" | jq --raw-output '.config.Labels."io.openshift.build.commit.id"') ||  {
        echo "Couldn't parse '.config.Labels."io.openshift.build.commit.id"' from image metadata!"
        return 1
    }
    image_commitref=$(echo "${image_metadata_config}" | jq --raw-output '.config.Labels."io.openshift.build.commit.ref"') ||  {
        echo "Couldn't parse '.config.Labels."io.openshift.build.commit.ref"' from image metadata!"
        return 1
    }
    image_created=$(echo "${image_metadata_config}" | jq --raw-output '.created') ||  {
        echo "Couldn't parse '.created' from image metadata!"
        return 1
    }

    local config_env
    local build_name_raw
    local openshift_build_name

    config_env=$(echo "${image_metadata_config}" | jq --raw-output '.config.Env') || {
        echo "Couldn't parse '.config.Env' from image metadata!"
        return 1
    }
    build_name_raw=$(echo "${config_env}" | grep '"OPENSHIFT_BUILD_NAME=') || {
        echo "Couldn't get 'OPENSHIFT_BUILD_NAME' from set of the image environment variables!"
        return 1
    }
    openshift_build_name=$(echo "${build_name_raw}" | sed 's/.*"OPENSHIFT_BUILD_NAME=\(.*\)".*/\1/') || {
        echo "Couldn't parse value of the 'OPENSHIFT_BUILD_NAME' variable from '${build_name_raw}'!"
        return 1
    }

    local image_metadata
    local image_size
    local image_size_mb

    image_metadata="$(skopeo inspect --raw "docker://${image_url}")" || {
        echo "Couldn't download image metadata with skopeo tool!"
        return 1
    }
    # Here we get the image size as a compressed image. This differs to what we gather in
    # 'tests/containers/base_image_test.py#test_image_size_change' where we check against the extracted image size.
    # There is no actual reason to compare these different sizes except that in this case we want to do check the
    # image remotely, whereas in the othe test, we have the image present locally on the machine.
    image_size=$(echo "${image_metadata}" | jq '[ .layers[].size ] | add') ||  {
        echo "Couldn't count image size from image metadata!"
        return 1
    }
    image_size_mb=$((image_size / 1024 / 1024)) ||  {
        echo "Couldn't count image size from image metadata!"
        return 1
    }

    test -n "${image_name}" || {
        echo "Couldn't retrieve the name of the image - got empty value!"
        return 1
    }

    echo "Image name retrieved: '${image_name}'"
    echo "Image created: '${image_created}'"
    echo "Image size: ${image_size_mb} MB"

    check_image_variable_matches_name_and_commitref_and_size "${image_variable}" "${image_name}" "${image_commitref}" \
        "${openshift_build_name}" "${image_size_mb}" || return 1

    check_image_commit_id_matches_metadata "${image_variable}" "${image_commit_id}" || return 1

    echo "---------------------------------------------"
}

# ------------------------------ release-1.2 SCRIPT --------------------------------- #

ret_code=0

echo "Starting check of image references in files: '${COMMIT_ENV_PATH}' and '${PARAMS_ENV_PATH}'"
echo "---------------------------------------------"

check_variables_uniq "${COMMIT_ENV_PATH}" "true" || {
    echo "ERROR: Variable names in the '${COMMIT_ENV_PATH}' file failed validation!"
    echo "----------------------------------------------------"
    ret_code=1
}

check_variables_uniq "${PARAMS_ENV_PATH}" "false" || {
    echo "ERROR: Variable names in the '${PARAMS_ENV_PATH}' file failed validation!"
    echo "----------------------------------------------------"
    ret_code=1
}

while IFS= read -r LINE; do
    echo "Checking format of: '${LINE}'"
    [[ "${LINE}" = *[[:space:]]* ]] && {
        echo "ERROR: Line contains white-space and it shouldn't!"
        echo "--------------------------------------------------"
        ret_code=1
        continue
    }
    [[ "${LINE}" != *=* ]] && {
        echo "ERROR: Line doesn't contain '=' and it should!"
        echo "----------------------------------------------"
        ret_code=1
        continue
    }

    IMAGE_VARIABLE=$(echo "${LINE}" | cut --delimiter '=' --field 1)
    IMAGE_URL=$(echo "${LINE}" | cut --delimiter '=' --field 2)

    test -n "${IMAGE_VARIABLE}" || {
        echo "ERROR: Couldn't parse image variable - got empty value!"
        echo "-------------------------------------------------------"
        ret_code=1
        continue
    }

    test -n "${IMAGE_URL}" || {
        echo "ERROR: Couldn't parse image URL - got empty value!"
        echo "--------------------------------------------------"
        ret_code=1
        continue
    }

    check_image "${IMAGE_VARIABLE}" "${IMAGE_URL}" || {
        echo "ERROR: Image definition for '${IMAGE_VARIABLE}' isn't okay!"
        echo "------------------------"
        ret_code=1
        continue
    }
done < "${PARAMS_ENV_PATH}"

echo ""
if test "${ret_code}" -eq 0; then
    echo "Validation of '${PARAMS_ENV_PATH}' was successful! Congrats :)"
else
    echo "The '${PARAMS_ENV_PATH}' file isn't valid, please check above!"
fi

exit "${ret_code}"
