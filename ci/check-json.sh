#!/bin/bash
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

shopt -s globstar

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
    else
	echo "    Ignoring as this file doesn't contain necessary key field '${string}' for check"
    fi

    return "${ret_code}"
}

ret_code=0
for f in **/*.yml **/*.yaml; do
    check_json "${f}" "opendatahub.io/notebook-software" || ret_code="${?}"
    check_json "${f}" "opendatahub.io/notebook-python-dependencies" || ret_code="${?}"
done

exit "${ret_code}"
