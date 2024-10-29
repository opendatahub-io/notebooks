#!/usr/bin/env bash
#
# This script serves to check YAML files in this repository that contain particular
# key fields where JSON string is expected. Such JSON strings are extracted and
# validated via `json_verify` tool.
#
# Local execution: ./ci/check-json.sh
#   Note: please execute from the root directory so that whole dir tree is checked
#
# In case of the PR on GitHub, this check is tied to GitHub actions automatically,
# see `.github/workflows` directory.

if ! shopt -s globstar; then
  echo "macOS ships bash-3.2 that does not know shopt -s globstar; install newer bash from homebrew"
  exit 1
fi

# yq: `brew install yq` or `apt-get install yq`
# json_verify: `brew install yajl` or `apt-get install yajl-tools`
for dep in yq json_verify; do
  if ! which -- ${dep} >/dev/null; then
    echo "the dependency ${dep} is not installed; install it now"
    exit 1
  fi
done

function check_json() {
    local f="${1}"
    local string="${2}"

    local ret_code=0

    echo "" # Let's make some space from eventual previous file check
    echo "Checking: '${f}' - for '${string}':"

    if grep --quiet --extended-regexp "${string}" "${f}"; then
    #if $(grep -e "${string}" "${f}"); then
        jsons=$(yq -r ".spec.tags[].annotations.\"${string}\"" "${f}")
        
        while IFS= read -r json; do
            echo "    ${json}"
            echo -n "  > "; echo "${json}" | json_verify || ret_code="${?}"
        done <<< "${jsons}"
        tmp_dir=$(mktemp --directory -t=check-jsons-in-file-)
    else
        echo "    Ignoring as this file doesn't contain necessary key field '${string}' for check"
    fi

    return "${ret_code}"
}

function split_yaml_file() {
    local filepath="${1}"
    local target_dir="${2}"

    local filename
    filename=$(echo "${filepath}" | sed 's#/#_#g') || return 1

    csplit --elide-empty-files -f "${target_dir}/${filename}_" -n 3 -s "${filepath}" '/^---$/' '{*}' || return 1

    return 0
}

function main() {
    local ret_code=0

    # Some yaml files can contain more definitions.
    # This is a problem for `yq` tool so we need to split these into separate files.
    local tmp_dir
    tmp_dir=$(mktemp --directory -t check-json-XXXXXXXXXX-)
    for f in **/*.yaml; do
        echo "Splitting the '${f}' file."
        split_yaml_file "${f}" "${tmp_dir}" || ret_code="${?}"
    done

    for f in "${tmp_dir}"/*; do
        check_json "${f}" "opendatahub.io/notebook-software" || ret_code="${?}"
        check_json "${f}" "opendatahub.io/notebook-python-dependencies" || ret_code="${?}"
    done

    exit "${ret_code}"
}

# allows sourcing the script into interactive session without executing it
if [[ "${0}" == "${BASH_SOURCE[0]}" ]]; then
    main
fi
