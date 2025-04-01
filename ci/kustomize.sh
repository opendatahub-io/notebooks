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

KUSTOMIZE_VERSION="${KUSTOMIZE_VERSION:-$DEFAULT_KUSTOMIZE_VERSION}"

function download_kustomize() {
    local tmp_dir="${1}"
    local kustomize_version="${2}"

    local kustomize_tar="${tmp_dir}/kustomize-${kustomize_version}.tar.gz"
    local kustomize_bin="${tmp_dir}/kustomize-${kustomize_version}"

    echo "---------------------------------------------------------------------------------"
    echo "Download kustomize '${kustomize_version}'"
    echo "---------------------------------------------------------------------------------"
    wget --output-document="${kustomize_tar}" "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize/v${kustomize_version}/kustomize_v${kustomize_version}_linux_amd64.tar.gz"
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
    find . -name "kustomization.yaml" | xargs dirname | grep -v "components" | xargs -t -I {} "${kustomize_bin}" build {} >"${kustomize_stdout}" 2>"${kustomize_stderr}"

    echo "Let's print the STDERR:"
    cat "${kustomize_stderr}"
}

function main() {
    local tmp_dir
    tmp_dir=$(mktemp --directory -t kustomize-XXXXXXXXXX)
    echo "Running in the following temporary directory: '${tmp_dir}'"

    download_kustomize "${tmp_dir}" "${KUSTOMIZE_VERSION}" || return 1
    execute_kustomize "${tmp_dir}" "${KUSTOMIZE_VERSION}" || return 1
}

# allows sourcing the script into interactive session without executing it
if [[ "${0}" == "${BASH_SOURCE[0]}" ]]; then
    main $@
fi
