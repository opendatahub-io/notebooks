#! /usr/bin/env bash

## Description:
##
## This script is intended to be invoked via the Makefile test-% target of the notebooks repository and assumes the deploy-% target
## has been previously executed.  It replaces the legacy 'validate-xxx-image' targets previously defined in the Makefile.
##
## The script will first check to ensure a notebook workload is running and have a k8s service object exposed.  Once verified:
##  - the relevant imagestream manifest from https://github.com/opendatahub-io/notebooks/tree/main/manifests/base is copied
##		into the running pod to act as the "source of truth" when asserting against installed version of py packages
##  - a test_notebook.ipynb will be copied into the running pod if it is defined in jupyter/*/test/test_notebook.ipynb
##      - for images inherited from the datascience notebook image, the minimal and datascience notebook test files are
##          sequentially copied into the running pod
##  - for each test_notebook.ipynb file that is copied into the running pod, a test suite is invoked via papermill
##      - test execution is considered failed if the papermill output contains the string 'FAILED'
##
## Currently this script only supports jupyter notebooks running on ubi9.
##
## Dependencies:
##
##    - git:        https://www.man7.org/linux/man-pages/man1/git.1.html
##    - kubectl:    https://kubernetes.io/docs/reference/kubectl/
##      - a local copy of kubectl is downloaded via the Makefile bin/kubectl target, and stored in bin/kubectl within the notebooks repo
##    - yq:         https://mikefarah.gitbook.io/yq
##      - a local copy of yq is downloaded via the Makefile bin/yq target, and stored in bin/yq within the notebooks repo
##    - wget:       https://www.man7.org/linux/man-pages/man1/wget.1.html
##    - curl:       https://www.man7.org/linux/man-pages/man1/curl.1.html
##    - lsof:       https://www.man7.org/linux/man-pages/man8/lsof.8.html
##    - kill:       https://www.man7.org/linux/man-pages/man1/kill.1.html
##
## Usage:
##
##      test_jupyter_with_papermill.sh <makefile test target>
##          - Intended to be invoked from the test-% target of the Makefile
##          - Arguments
##              - <makefile test target>
##                  - the resolved wildcard value from the Makefile test-% pattern-matching rule
##
##


set -exuo pipefail

# Description:
#   TODO
#
# Inputs:
#   $kbin
#   $workbench_directory
#
# Returns:
#   Stringified YAML document corresponding to output of kustomization.yaml for given workbench directory
function _get_manifest_yaml()
{
    local manifest_yaml=
    manifest_yaml=$(${kbin} kustomize "${workbench_directory}/kustomize/base")

    printf '%s' "${manifest_yaml}"
}



# Description:
#   Returns the workload resource app name as defined by the app label of the relevant kustomization.yaml
#   Unfortunately a necessary preprocessing function due to current inconsistencies with how rstudio
#   is structured
#
# Inputs:
#   $supported_accelerators
#   $workbench_accelerator
#   $workbench_feature
#   $workbench_scope
#   $workbench_os
#   $workbench_python
#
# Returns:
#   Name of the workload resource app label
function _get_workload_app_name()
{
    local app_name=
    app_name=$(${yqbin} eval 'select(.kind == "Pod" or .kind == "StatefulSet").metadata.labels.app' <<< "${manifest_yaml}")

    printf '%s' "${app_name}"
}

# Description:
#   TODO
#
# Returns:
#   Open port on the system in the range of 8000-9999 (if one exists)
find_open_port() {
  if ! command -v lsof &>/dev/null; then
    echo "Error: lsof is not installed." >&2
    return 1
  fi

  for port in {8000..9999}; do
    if ! lsof "-iTCP:${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
      printf '%s' "${port}"
      return 0
    fi
  done

  return 1
}


# Description:
#   A blocking function that queries the cluster to until the workbench workload enters a Ready state
#	Once the workload is Ready, if its a jupyter-related workbench, the function will port-forward to
#   the relevant Service resource and attempt to ping the Jupyterlab API endpoint.  Upon success, the
#   port-forward process is terminated.
#
# Arguments:
#   $1 : Name of the workload as defined by the workload app label
#
# Inputs:
#   $workbench_feature
#
# Returns:
#   Name of the notebook as defined by the workload app label
function _wait_for_workload()
{
    local workload_app_name="${1:-}"

    "${kbin}" wait --for=condition=ready pod -l app="${workload_app_name}" --timeout=900s

    local ide_server_port=
    ide_server_port=$(${yqbin} eval 'select(.kind == "Pod" or .kind == "StatefulSet") | .. | select(has("ports")) | .ports[] | select(.name == "workbench-port") | .containerPort' <<< "${manifest_yaml}")

    local ide_server_port=
    local ide_server_endpoint=
    local k8s_resource=
    case "${workbench_feature}" in
        jupyter)
            ide_server_endpoint="/notebook/opendatahub/jovyan/api"
            k8s_resource="service"
            ;;
        codeserver | rstudio)
            ide_server_endpoint=""
            k8s_resource="pod"
            ;;
        runtime)
            ;;
        *)
            ;;
    esac

    if [ -n "${ide_server_port}" ] && [ -n "${k8s_resource}" ]; then
        local local_port=
        local_port=$(find_open_port)
        "${kbin}" port-forward "${k8s_resource}/${workload_app_name}-workbench" "${local_port}:${ide_server_port}" &
        local pf_pid=$!
        local ide_server_url="http://localhost:${local_port}${ide_server_endpoint}"
        curl --retry 5 --retry-delay 5 --retry-connrefused "${ide_server_url}";
        kill ${pf_pid}
    fi
}

# Description:
#   TODO
#
# Inputs:
#   $workbench_feature
#
# Returns:
#   Space-delimited string with all the commands expected to be available for a given workload container
function _get_required_commands()
{
    local base_required_commands=("curl" "python3" "oc" "skopeo")

    local feature_specific_commands=
    case "${workbench_feature}" in
        jupyter)
            feature_specific_commands=()
            ;;
        codeserver)
            feature_specific_commands=("code-server")
            ;;
        rstudio)
            feature_specific_commands=("/usr/lib/rstudio-server/bin/rserver")
            ;;
        runtime)
            feature_specific_commands=()
            ;;
        *)
            feature_specific_commands=()
            ;;
    esac

    local required_commands=("${base_required_commands[@]}" "${feature_specific_commands[@]}")

    local all_commands=
    all_commands=$(printf '%s ' "${required_commands[@]}")

    printf '%s' "${all_commands%[[:space:]]*}"

}

# Description:
# 	TODO
#
# Inputs:
#   $workload_name
#
# Returns:
#   - 0 if all checks succeed
#   - 1 if one or more of the checks fail
function _test_jupyter()
{
    # shellcheck disable=SC1091
    source "${root_repo_directory}/scripts/makefile_utils/_jupyter_test_helper.sh"

    _create_jupyter_workbench_test_versions_source_of_truth

    "${kbin}" exec "${workload_name}" -- /bin/sh -c "python3 -m pip install papermill"

    if _jupyter_workbench_derived_from_datascience ; then
        _test_jupyter_datascience_workbench
    fi

    if ! [ "${workbench_scope}" = 'datascience' ]; then
        _run_jupyter_papermill_test "${workbench_scope}"
    fi
}

# Description:
# 	Placeholder function included for consistency.  Presently we have no container tests defined specifically for codeserver.
#
function _test_codeserver()
{
    :
}

# Description:
# 	TODO
#
# Inputs:
#   $workload_name
#
# Returns:
#   - 0 if all checks succeed
#   - 1 if one or more of the checks fail
function _test_rstudio()
{

    local target_directory="/opt/app-root/src"
    local temp_library_directory="${target_directory}/R/temp-library"

    local fail=
	${kbin} exec "${workload_name}" -- mkdir -p "${temp_library_directory}" > /dev/null 2>&1
	if ${kbin} exec "${workload_name}" -- R -e "install.packages('tinytex', lib='${temp_library_directory}')" > /dev/null 2>&1 ; then
		printf '%s\n' "Tinytex installation successful!"
	else
		printf '%s\n' "**ERROR**: Tinytex installation failed."
        fail=1
	fi

    local test_filename="test_script.R"
    local target_directory="/opt/app-root/src/"
	${kbin} cp "${root_repo_directory}/${workbench_directory}/test/${test_filename}" "${workload_name}:${target_directory}/${test_filename}" > /dev/null 2>&1
	if ${kbin} exec "${workload_name}" -- Rscript "${target_directory}/${test_filename}" > /dev/null 2>&1 ; then
		printf '%s\n' "R script executed successfully!"
	else
		printf '%s\n' "**ERROR**: R script failed."
		fail=1
	fi

	if [ "${fail:-0}" -eq 1 ]; then
		return 1
	fi;
}

# Description:
# 	TODO
#
# Inputs:
#   $workload_name
#
# Returns:
#   - 0 if all checks succeed
#   - 1 if one or more of the checks fail
function _test_runtime()
{
    if ! ${kbin} exec "${workload_name}" -- /bin/sh -c "curl https://raw.githubusercontent.com/opendatahub-io/elyra/refs/heads/main/etc/generic/requirements-elyra.txt --output req.txt && \
            python3 -m pip install -r req.txt > /dev/null && \
            curl https://raw.githubusercontent.com/nteract/papermill/main/papermill/tests/notebooks/simple_execute.ipynb --output simple_execute.ipynb && \
            python3 -m papermill simple_execute.ipynb output.ipynb > /dev/null" ; then
        printf '%s\n' "**ERROR**: Image does not meet Python requirements criteria in pipfile"
        return 1
    fi
}

# Description:
# 	TODO
#
# Inputs:
#   $workload_name
#
# Returns:
#   - 0 if all checks succeed
#   - 1 if one or more of the checks fail
function _feature_specific_testing()
{
    case "${workbench_feature}" in
        jupyter)
            _test_jupyter
            ;;
        codeserver)
            _test_codeserver
            ;;
        rstudio)
            _test_rstudio
            ;;
        runtime)
            _test_runtime
            ;;
        *)
            ;;
    esac
}


# Description:
# 	TODO
#
# Inputs:
#   $workload_name
#   $kbin
#
# Returns:
#   - 0 if all checks succeed
#   - 1 if one or more of the checks fail
function _verify_commands_present()
{
    local commands=
    commands=$(_get_required_commands)

    local fail=
	for cmd in ${commands}; do
		printf "=> Checking workload '%s' for presence of '%s'...\n" "${workload_name}" "${cmd}"
		if ! ${kbin} exec "${workload_name}" which $cmd > /dev/null 2>&1 ; then
			printf '\t%s\n' "**ERROR** '${cmd}' not found"
			fail=1
			continue
		fi
	done

	if [ "${fail:-0}" -eq 1 ]; then
		return 1
	else
		printf "=> Workload '%s' contains all required commands" "${workload_name}"
	fi;
}

# Description:
# 	TODO
#
# Inputs:
#   $workload_name
#
# Returns:
#   - 0 if all checks succeed
#   - 1 if one or more of the checks fail
function _handle_test()
{
    _verify_commands_present
    _feature_specific_testing

}

workbench_accelerator="${1:-}"
workbench_feature="${2:-}"
workbench_scope="${3:-}"
workbench_os="${4:-}"
workbench_python="${5:-}"
workbench_directory="${6:-}"

root_repo_directory=$(readlink -f "$(git rev-parse --show-toplevel)")

kbin=$(readlink -f "${root_repo_directory}/bin/kubectl")
if ! [ -e "${kbin}" ]; then
    printf "%s" "missing bin/kubectl"
    exit 1
fi

yqbin=$(readlink -f "${root_repo_directory}/bin/yq")
if ! [ -e "${yqbin}" ]; then
    printf "%s" "missing bin/yq"
    exit 1
fi

printf '%s: %s\n' "workbench_accelerator" "${workbench_accelerator}"
printf '%s: %s\n' "workbench_feature" "${workbench_feature}"
printf '%s: %s\n' "workbench_scope" "${workbench_scope}"
printf '%s: %s\n' "workbench_os" "${workbench_os}"
printf '%s: %s\n' "workbench_python" "${workbench_python}"
printf '%s: %s\n' "workbench_directory" "${workbench_directory}"

manifest_yaml=$(_get_manifest_yaml)

workload_app_name=$( _get_workload_app_name )

printf '%s\n' "Waiting for app=${workload_app_name} workload to be ready.  This could take a few minutes..."
_wait_for_workload "${workload_app_name}"

workload_name=$("${kbin}" get pods -l app="${workload_app_name}" -o jsonpath='{.items[0].metadata.name}')

_handle_test


