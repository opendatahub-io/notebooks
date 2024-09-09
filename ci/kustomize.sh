#!/bin/bash

# This script serves to validate our kustomize files/manifests with respect of the given kustomize version.
# We use this to verify that there is no warning and not errors
#
# Local execution: [KUSTOMIZE_VERSION=5.3.1] ./ci/kustomize.sh
#   Note: please execute from the root directory so that whole dir tree is checked
#
# In case of the PR on GitHub, this check is tied to GitHub actions automatically,
# see `.github/workflows` directory.


# The default kustomize version that is determined based on what is currently used in the [rhods|opendatahub]-operator in runtime:
# https://github.com/red-hat-data-services/rhods-operator/blob/7ccc405135f99c014982d7e297b8949e970dd750/go.mod#L28-L29
# and then to match appropriate kustomize release https://github.com/kubernetes-sigs/kustomize/releases/tag/kustomize%2Fv5.0.3
DEFAULT_KUSTOMIZE_VERSION=5.0.3
# The latest kustomize version we want to check with to be sure we're prepared for the future
THE_LATEST_KUSTOMIZE=5.6.0

KUSTOMIZE_VERSION="${KUSTOMIZE_VERSION:-$DEFAULT_KUSTOMIZE_VERSION}"

function download_kustomize() {
    local tmp_dir="${1}"
    local kustomize_version="${2}"

    local kustomize_tar="${tmp_dir}/kustomize-${kustomize_version}.tar.gz"
    local kustomize_bin="${tmp_dir}/kustomize-${kustomize_version}"

    echo "---------------------------------------------------------------------------------"
    echo "Download kustomize '${kustomize_version}'"
    echo "---------------------------------------------------------------------------------"

    # Detect OS
    local uname_out
    uname_out="$(uname -s)"
    case "${uname_out}" in
        Linux*)     os=linux;;
        Darwin*)    os=darwin;;
        *)          echo "Unsupported OS: ${uname_out}" && return 1;;
    esac

    # Detect architecture
    local arch
    arch="$(uname -m)"
    case "${arch}" in
        x86_64)   arch=amd64;;
        arm64)    arch=arm64;;
        aarch64)  arch=arm64;;
        *)        echo "Unsupported architecture: ${arch}" && return 1;;
    esac

    local download_url="https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize/v${kustomize_version}/kustomize_v${kustomize_version}_${os}_${arch}.tar.gz"
    echo "Downloading from: ${download_url}"

    wget --output-document="${kustomize_tar}" "${download_url}"
    tar -C "${tmp_dir}" -xvf "${kustomize_tar}"
    mv "${tmp_dir}/kustomize" "${kustomize_bin}"

    "${kustomize_bin}" version
}

function execute_kustomize() {
    local tmp_dir="${1}"
    local kustomize_version="${2}"

    local kustomize_stdout="${tmp_dir}/kustomize-${kustomize_version}-stdout.yaml"
    local kustomize_stderr="${tmp_dir}/kustomize-${kustomize_version}-stderr.txt"
    local kustomize_bin="${tmp_dir}/kustomize-${kustomize_version}"

    echo "---------------------------------------------------------------------------------------------------"
    echo "Starting to run kustomize '${kustomize_version}' for each kustomization.yaml file except components"
    echo "---------------------------------------------------------------------------------------------------"
    # We don't want to execute kustomization on the components part as it's not intended to be used that way.
    # This first run is for the actual execution to get the generated output and eventual errors/warnings.
    find . -name "kustomization.yaml" | xargs dirname | grep -v "components" | xargs -I {} "${kustomize_bin}" build {} >"${kustomize_stdout}" 2>"${kustomize_stderr}"
    # This second run is with verbose output to see eventual errors/warnings together with which command they are present for easier debugging.
    find . -name "kustomization.yaml" | xargs dirname | grep -v "components" | xargs --verbose -I {} "${kustomize_bin}" build {} >/dev/null

    echo "Let's print the STDERR:"
    cat "${kustomize_stderr}"
}

function check_the_results() {
    local tmp_dir="${1}"
    local kustomize_version_1="${2}"
    local kustomize_version_2="${3}"

    local kustomize_stdout_1="${tmp_dir}/kustomize-${kustomize_version_1}-stdout.yaml"
    local kustomize_stderr_1="${tmp_dir}/kustomize-${kustomize_version_1}-stderr.txt"
    local kustomize_stdout_2="${tmp_dir}/kustomize-${kustomize_version_2}-stdout.yaml"
    local kustomize_stderr_2="${tmp_dir}/kustomize-${kustomize_version_2}-stderr.txt"

    echo "---------------------------------------------------------------------------------"
    echo "Checking the generated outputs - should be identical:"
    echo "  - ${kustomize_stdout_1}"
    echo "  - ${kustomize_stdout_2}"
    echo "---------------------------------------------------------------------------------"
    diff -u "${kustomize_stdout_1}" "${kustomize_stdout_2}" || {
        echo "Generated files from kustomize differs between kustomize version ${kustomize_version_1} and ${kustomize_version_2}. Please check above!"
        return 1
    }

    echo "---------------------------------------------------------------------------------"
    echo "No log in STDERR outputs should be printed:"
    echo "  - ${kustomize_stderr_1}"
    echo "  - ${kustomize_stderr_2}"
    echo "---------------------------------------------------------------------------------"
    if [ -s "${kustomize_stderr_1}" ] || [ -s "${kustomize_stderr_2}" ]; then
        echo "There were some logs generated to STDERR during the kustomize build. Please check the log above!"
        return 1
    fi
}

function run_check() {
    local tmp_dir="${1}"
    local kustomize_version="${2}"

    download_kustomize "${tmp_dir}" "${kustomize_version}" || return 1
    execute_kustomize "${tmp_dir}" "${kustomize_version}" || return 1
}

function main() {
    local ret_code=0

    local tmp_dir
    tmp_dir=$(mktemp --directory -t kustomize-XXXXXXXXXX)
    echo "Running in the following temporary directory: '${tmp_dir}'"

    run_check "${tmp_dir}" "${KUSTOMIZE_VERSION}" || return 1
    run_check "${tmp_dir}" "${THE_LATEST_KUSTOMIZE}" || return 1

    # --------------------------------------------------------------------------------------

    check_the_results "${tmp_dir}" "${KUSTOMIZE_VERSION}" "${THE_LATEST_KUSTOMIZE}" || return 1

    exit "${ret_code}"
}

# allows sourcing the script into interactive session without executing it
if [[ "${0}" == "${BASH_SOURCE[0]}" ]]; then
    main "$@"
fi
