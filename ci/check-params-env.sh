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
EXPECTED_NUM_RECORDS=20

# ---------------------------- DEFINED FUNCTIONS ----------------------------- #

function check_variables_uniq() {
    local env_file_path="${1}"
    local ret_code=0

    echo "Checking that all variables in the file '${env_file_path}' are unique and expected"

    local content
    content=$(sed 's#\(.*\)=.*#\1#' "${env_file_path}" | sort)

    local num_records
    num_records=$(echo "${content}" | wc -l)

    local num_uniq_records
    num_uniq_records=$(echo "${content}" | uniq | wc -l)

    test "${num_records}" -eq "${num_uniq_records}" || {
        echo "Some of the records in the file aren't unique!"
        ret_code=1
    }

    test "${num_records}" -eq "${EXPECTED_NUM_RECORDS}" || {
        echo "Number of records in the file is incorrect - expected '${EXPECTED_NUM_RECORDS}' but got '${num_records}'!"
        ret_code=1
    }

    echo "---------------------------------------------"
    return "${ret_code}"
}

function check_image_variable_matches_name_and_commitref() {
    local image_variable="${1}"
    local image_name="${2}"
    local image_commitref="${3}"
    local openshift_build_name="${4}"

    local expected_name
    local expected_commitref
    local expected_build_name  # Why some of the images has `-amd64` suffix and others not?
    case "${image_variable}" in
        odh-minimal-notebook-image-n)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="jupyter-minimal-ubi9-python-3.9-amd64"
            ;;
        odh-minimal-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="jupyter-minimal-ubi9-python-3.9-amd64"
            ;;
        odh-minimal-gpu-notebook-image-n)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.9-amd64"
            ;;
        odh-minimal-gpu-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-minimal-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="cuda-jupyter-minimal-ubi9-python-3.9-amd64"
            ;;
        odh-pytorch-gpu-notebook-image-n)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="jupyter-pytorch-ubi9-python-3.9-amd64"
            ;;
        odh-pytorch-gpu-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-pytorch-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="jupyter-pytorch-ubi9-python-3.9-amd64"
            ;;
        odh-generic-data-science-notebook-image-n)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="jupyter-datascience-ubi9-python-3.9-amd64"
            ;;
        odh-generic-data-science-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-datascience-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="jupyter-datascience-ubi9-python-3.9-amd64"
            ;;
        odh-tensorflow-gpu-notebook-image-n)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.9-amd64"
            ;;
        odh-tensorflow-gpu-notebook-image-n-1)
            expected_name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="cuda-jupyter-tensorflow-ubi9-python-3.9-amd64"
            ;;
        odh-trustyai-notebook-image-n)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="jupyter-trustyai-ubi9-python-3.9-amd64"
            ;;
        odh-trustyai-notebook-image-n-1)
            expected_name="odh-notebook-jupyter-trustyai-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="jupyter-trustyai-ubi9-python-3.9-amd64"
            ;;
        odh-habana-notebook-image-n)
            expected_name="odh-notebook-habana-jupyter-1.13.0-ubi8-python-3.8"
            expected_commitref="2024a"
            expected_build_name="habana-jupyter-1.13.0-ubi8-python-3.8-amd64"
            ;;
        odh-habana-notebook-image-n-1)
            expected_name="odh-notebook-habana-jupyter-1.10.0-ubi8-python-3.8"
            expected_commitref="2023b"
            expected_build_name="habana-jupyter-1.10.0-ubi8-python-3.8-amd64"
            ;;
        odh-codeserver-notebook-image-n)
            expected_name="odh-notebook-code-server-ubi9-python-3.9"
            expected_commitref="2024a"
            expected_build_name="codeserver-ubi9-python-3.9-amd64"
            ;;
        odh-codeserver-notebook-image-n-1)
            expected_name="odh-notebook-code-server-ubi9-python-3.9"
            expected_commitref="2023b"
            expected_build_name="codeserver-ubi9-python-3.9-amd64"
            ;;
        odh-rstudio-notebook-image-n)
            expected_name="odh-notebook-rstudio-server-c9s-python-3.9"
            expected_commitref="2024a"
            expected_build_name="rstudio-c9s-python-3.9-amd64"
            ;;
        odh-rstudio-notebook-image-n-1)
            expected_name="odh-notebook-rstudio-server-c9s-python-3.9"
            expected_commitref="2023b"
            expected_build_name="rstudio-c9s-python-3.9-amd64"
            ;;
        # For both RStudio GPU workbenches - the final name labels are identical to plain RStudio ones
        # This is because the very same RStudio Dockerfile is used but different base images in both cases
        # We should consider what to do with this - in ideal case, we should have different labels for these cases.
        odh-rstudio-gpu-notebook-image-n)
            expected_name="odh-notebook-rstudio-server-c9s-python-3.9"
            expected_commitref="2024a"
            expected_build_name="cuda-rstudio-c9s-python-3.9-amd64"
            ;;
        odh-rstudio-gpu-notebook-image-n-1)
            expected_name="odh-notebook-rstudio-server-c9s-python-3.9"
            expected_commitref="2023b"
            expected_build_name="cuda-rstudio-c9s-python-3.9-amd64"
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

    local image_metadata
    local image_name
    local image_commit_id
    local image_commitref

    image_metadata="$(skopeo inspect --config "docker://${image_url}")" || {
        echo "Couldn't download image metadata with skopeo tool!"
        return 1
    }
    image_name=$(echo "${image_metadata}" | jq --raw-output '.config.Labels.name') ||  {
        echo "Couldn't parse '.config.Labels.name' from image metadata!"
        return 1
    }
    image_commit_id=$(echo "${image_metadata}" | jq --raw-output '.config.Labels."io.openshift.build.commit.id"') ||  {
        echo "Couldn't parse '.config.Labels."io.openshift.build.commit.id"' from image metadata!"
        return 1
    }
    image_commitref=$(echo "${image_metadata}" | jq --raw-output '.config.Labels."io.openshift.build.commit.ref"') ||  {
        echo "Couldn't parse '.config.Labels."io.openshift.build.commit.ref"' from image metadata!"
        return 1
    }

    local config_env
    local build_name_raw
    local openshift_build_name

    config_env=$(echo "${image_metadata}" | jq --raw-output '.config.Env') || {
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

    test -n "${image_name}" || {
        echo "Couldn't retrieve the name of the image - got empty value!"
        return 1
    }

    echo "Image name retrieved: '${image_name}'"

    check_image_variable_matches_name_and_commitref "${image_variable}" "${image_name}" "${image_commitref}" "${openshift_build_name}" || return 1

    check_image_commit_id_matches_metadata "${image_variable}" "${image_commit_id}" || return 1

    echo "---------------------------------------------"
}

# ------------------------------ MAIN SCRIPT --------------------------------- #

ret_code=0

echo "Starting check of image references in files: '${COMMIT_ENV_PATH}' and '${PARAMS_ENV_PATH}'"
echo "---------------------------------------------"

check_variables_uniq "${COMMIT_ENV_PATH}" || {
    echo "ERROR: Variable names in the '${COMMIT_ENV_PATH}' file failed validation!"
    echo "----------------------------------------------------"
    ret_code=1
}

check_variables_uniq "${PARAMS_ENV_PATH}" || {
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