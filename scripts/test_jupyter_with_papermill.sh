#! /usr/bin/env bash

## Description:
##
## This script is intended to be invoked via the Makefile test-% target of the notebooks repository and assumes the deploy9-% target
## has been previously executed.  It replaces the legacy 'test_with_papermill' function previously defined in the Makefile.
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


set -uxo pipefail

# Description:
#   Returns the underlying operating system of the notebook based on the notebook name
#		- presently, all jupyter notebooks run on ubi9
#
# Arguments:
#   $1 : Name of the notebook workload running on the cluster
#
# Returns:
#   Name of operating system for the notebook or empty string if not recognized
function _get_os_flavor()
{
    local full_notebook_name="${1:-}"

    local os_flavor=
    case "${full_notebook_name}" in
        *ubi9-*)
            os_flavor='ubi9'
            ;;
        *)
            ;;
    esac

    printf '%s' "${os_flavor}"
}

# Description:
#   Returns the accelerator of the notebook based on the notebook name
#		- Due to existing build logic, cuda- prefix missing on pytorch target name
#
# Arguments:
#   $1 : Name of the notebook workload running on the cluster
#
# Returns:
#   Name of accelerator required for the notebook or empty string if none required
function _get_accelerator_flavor()
{
    local full_notebook_name="${1:-}"

    local accelerator_flavor=
    case "${full_notebook_name}" in
        *cuda-* | jupyter-pytorch-*)
            accelerator_flavor='cuda'
            ;;
        *rocm-*)
            accelerator_flavor='rocm'
            ;;
        *)
            ;;
    esac

    printf '%s' "${accelerator_flavor}"
}

# Description:
#   Returns the absolute path of notebook resources in the notebooks/ repo based on the notebook name
#
# Arguments:
#   $1 : Name of the notebook identifier
#   $2 : [optional] Subdirectory to append to computed absolute path
#		- path should NOT start with a leading /
#
# Returns:
#   Absolute path to the jupyter notebook directory for the given notebook test target
function _get_jupyter_notebook_directory()
{
    local notebook_id="${1:-}"
    local subpath="${2:-}"

    local jupyter_base="${root_repo_directory}/jupyter"
    local directory="${jupyter_base}/${notebook_id}/${os_flavor}-${python_flavor}${subpath:+"/$subpath"}"

    printf '%s' "${directory}"
}

# Description:
#   Returns the notebook name as defined by the app label of the relevant kustomization.yaml
#   Unfortunately a necessary preprocessing function due to numerous naming inconsistencies
#   with the Makefile targets and notebooks repo
#
# Arguments:
#   $1 : Value of the test-% wildcard from the notebooks repo Makefile
#
# Returns:
#   Name of the notebook as defined by the workload app label
function _get_notebook_name()
{
    local test_target="${1:-}"

    local raw_notebook_name=
    raw_notebook_name=$( tr '.' '-' <<< "${test_target#'cuda-'}" )

    local jupyter_notebook_prefix='jupyter'
    local rocm_target_prefix="rocm-${jupyter_notebook_prefix}"

    local notebook_name=
    case "${raw_notebook_name}" in
        *$jupyter_minimal_notebook_id*)
            local jupyter_stem="${raw_notebook_name#*"$jupyter_notebook_prefix"}"
            notebook_name="${jupyter_notebook_prefix}${jupyter_stem}"
            ;;
        $rocm_target_prefix*)
            notebook_name=jupyter-rocm${raw_notebook_name#"$rocm_target_prefix"}
            ;;
        *)
            notebook_name="${raw_notebook_name}"
            ;;
    esac

    printf '%s' "${notebook_name}"
}

# Description:
#   A blocking function that queries the cluster to until the notebook workload enters a Ready state
#	Once the workload is Ready, the function will port-forward to the relevant Service resource and attempt
#   to ping the Jupyterlab API endpoint.  Upon success, the port-forward process is terminated.
#
# Arguments:
#   $1 : Name of the notebook as defined by the workload app label
#
# Returns:
#   Name of the notebook as defined by the workload app label
function _wait_for_workload()
{
    local notebook_name="${1:-}"

    "${kbin}" wait --for=condition=ready pod -l app="${notebook_name}" --timeout=600s
    "${kbin}" port-forward "svc/${notebook_name}-notebook" 8888:8888 &
    local pf_pid=$!
    curl --retry 5 --retry-delay 5 --retry-connrefused http://localhost:8888/notebook/opendatahub/jovyan/api ;
    kill ${pf_pid}
}

# Description:
#   Computes the absolute path of the imagestream manifest for the notebook under test
#
# Arguments:
#   $1 : Name of the notebook identifier
#
# Returns:
#   Absolute path to the iamgestream manifest file corresponding to the notebook under test
function _get_source_of_truth_filepath()
{
    local notebook_id="${1##*/}"

    local manifest_directory="${root_repo_directory}/manifests"
    local imagestream_directory=
    local file_suffix=
    local filename=
    case "${python_flavor}" in
        python-3.12)
            imagestream_directory="${manifest_directory}/overlays/additional"
            file_suffix='-imagestream.yaml'

            local imagestream_accelerator_flavor="${accelerator_flavor:-cpu}"
            filename="jupyter-${notebook_id}-${imagestream_accelerator_flavor}-py312-${os_flavor}-${file_suffix}"
            ;;
        *)
            imagestream_directory="${manifest_directory}/base"
            file_suffix='notebook-imagestream.yaml'

            case "${notebook_id}" in
                *$jupyter_minimal_notebook_id*)
                    filename="jupyter-${accelerator_flavor:+"$accelerator_flavor"-}${notebook_id}-${file_suffix}"
                    if [ "${accelerator_flavor}" = 'cuda' ]; then
                        filename="jupyter-${notebook_id}-gpu-${file_suffix}"
                    fi
                    ;;
                *$jupyter_datascience_notebook_id* | *$jupyter_trustyai_notebook_id*)
                    filename="jupyter-${notebook_id}-${file_suffix}"
                    ;;
                *$jupyter_pytorch_notebook_id* | *$jupyter_tensorflow_notebook_id*)
                    filename="jupyter-${accelerator_flavor:+"$accelerator_flavor"-}${notebook_id}-${file_suffix}"
                    if [ "${accelerator_flavor}" = 'cuda' ]; then
                        filename="jupyter-${notebook_id}-${file_suffix}"
                    fi
                    ;;
            esac
            ;;
    esac


    local filepath="${imagestream_directory}/${filename}"

    if ! [ -e "${filepath}" ]; then
        printf '%s\n' "Unable to determine imagestream manifest for '${test_target}'.  Computed filepath '${filepath}' does not exist."
        exit 1
    fi

    printf '%s' "${filepath}"
}

# Description:
#   Creates an 'expected_version.json' file based on the relevant imagestream manifest within the notebooks repo relevant to the notebook under test on the
#   running pod to be used as the "source of truth" for test_notebook.ipynb tests that assert on package version.
#
#	Each test suite that asserts against package versions must include necessary logic to honor this file.
#
# Arguments:
#   $1 : Name of the notebook identifier
function _create_test_versions_source_of_truth()
{
    local notebook_id="${1:-}"

    local version_filename='expected_versions.json'

    local test_version_truth_filepath=
    test_version_truth_filepath="$( _get_source_of_truth_filepath "${notebook_id}" )"

    local nbdime_version='4.0'
    local nbgitpuller_version='1.2'

    expected_versions=$("${yqbin}" '.spec.tags[0].annotations | .["opendatahub.io/notebook-software"] + .["opendatahub.io/notebook-python-dependencies"]' "${test_version_truth_filepath}" |
        "${yqbin}" -N -p json -o yaml |
        nbdime_version=${nbdime_version} nbgitpuller_version=${nbgitpuller_version} "${yqbin}" '. + [{"name": "nbdime", "version": strenv(nbdime_version)},{"name": "nbgitpuller", "version": strenv(nbgitpuller_version)}]' |
        "${yqbin}" -N -o json '[ .[] | (.name | key) = "key" | (.version | key) = "value" ] | from_entries')

    # Following disabled shellcheck intentional as the intended behavior is for those ${1}, ${2} variables to only be expanded when running within kubernetes
    # shellcheck disable=SC2016
    "${kbin}" exec "${notebook_workload_name}" -- /bin/sh -c 'touch "${1}"; printf "%s\n" "${2}" > "${1}"' -- "${version_filename}" "${expected_versions}"
}

# Description:
#   Main "test runner" function that copies the relevant test_notebook.ipynb file for the notebook under test into
#	the running pod and then invokes papermill within the pod to actually execute test suite.
#
#	Script will return non-zero exit code in the event all unit tests were not successfully executed.  Diagnostic messages
#	are printed in the event of a failure.
#
# Arguments:
#   $1 : Name of the notebook identifier
function _run_test()
{
    local notebook_id="${1:-}"

    local test_notebook_file='test_notebook.ipynb'
    local repo_test_directory=
    repo_test_directory="$(_get_jupyter_notebook_directory "${notebook_id}" "test")"
    local output_file_prefix=
    output_file_prefix=$(tr '/' '-' <<< "${notebook_id}_${os_flavor}")

    "${kbin}" cp "${repo_test_directory}/${test_notebook_file}" "${notebook_workload_name}:./${test_notebook_file}"

	if ! "${kbin}" exec "${notebook_workload_name}" -- /bin/sh -c "export IPY_KERNEL_LOG_LEVEL=DEBUG; python3 -m papermill ${test_notebook_file} ${output_file_prefix}_output.ipynb --kernel python3 --log-level DEBUG --stderr-file ${output_file_prefix}_error.txt" ; then
		echo "ERROR: The ${notebook_id} ${os_flavor} notebook encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-${notebook_id}-${os_flavor}-${python_flavor}-test-e2e' directory or run 'cat ${output_file_prefix}_error.txt' within your container. The make process has been aborted."
		exit 1
	fi

    local test_result=
    test_result=$("${kbin}" exec "${notebook_workload_name}" -- /bin/sh -c "grep FAILED ${output_file_prefix}_error.txt" 2>&1)
    case "$?" in
        0)
            printf '\n\n%s\n' "ERROR: The ${notebook_id} ${os_flavor} notebook encountered a test failure. The make process has been aborted."
            "${kbin}" exec "${notebook_workload_name}" -- /bin/sh -c "cat ${output_file_prefix}_error.txt"
            exit 1
            ;;
        1)
            printf '\n%s\n\n' "The ${notebook_id} ${os_flavor} notebook tests ran successfully"
            ;;
        2)
            printf '\n\n%s\n' "ERROR: The ${notebook_id} ${os_flavor} notebook encountered an unexpected failure. The make process has been aborted."
            printf '%s\n\n' "${test_result}"
            exit 1
            ;;
        *)
    esac
}

# Description:
#	Checks if the notebook under test is derived from the datasciences notebook.  This determination is subsequently used to know whether or not
#	additional papermill tests should be invoked against the running notebook resource.
#
#	The notebook_id argument provided to the function is simply checked against a hard-coded array of notebook ids known to inherit from the
# 	datascience notebook.
#
#	Returns successful exit code if the notebook inherits from the datascience image.
#
# Arguments:
#   $1 : Name of the notebook identifier
function _image_derived_from_datascience()
{
    local notebook_id="${1:-}"

    local datascience_derived_images=("${jupyter_datascience_notebook_id}" "${jupyter_trustyai_notebook_id}" "${jupyter_tensorflow_notebook_id}" "${jupyter_pytorch_notebook_id}")

    printf '%s\0' "${datascience_derived_images[@]}" | grep -Fz -- "${notebook_id}"
}

# Description:
#	Convenience function that will invoke the minimal and datascience papermill tests against the running notebook workload
function _test_datascience_notebook()
{
    _run_test "${jupyter_minimal_notebook_id}"
    _run_test "${jupyter_datascience_notebook_id}"
}

# Description:
# 	"Orchestration" function computes necessary parameters and prepares the running notebook workload for papermill tests to be invoked
#		- notebook_id is calculated based on the workload name and computed accelerator value
#		- Appropriate "source of truth" file to be used in asserting package version is copied into the running pod
#		- papermill is installed on the running pod
#		- All relevant tests based on the notebook_id are invoked
function _handle_test()
{
    local notebook_id=

    # Due to existing logic - cuda accelerator value needs to be treated as empty string
    local accelerator_flavor="${accelerator_flavor}"
    accelerator_flavor="${accelerator_flavor##'cuda'}"


    case "${notebook_workload_name}" in
        *${jupyter_minimal_notebook_id}-*)
            notebook_id="${jupyter_minimal_notebook_id}"
            ;;
        *${jupyter_datascience_notebook_id}-*)
            notebook_id="${jupyter_datascience_notebook_id}"
            ;;
        *-${jupyter_trustyai_notebook_id}-*)
            notebook_id="${jupyter_trustyai_notebook_id}"
            ;;
        *${jupyter_tensorflow_notebook_id}-*)
            notebook_id="${accelerator_flavor:+$accelerator_flavor/}${jupyter_tensorflow_notebook_id}"
            ;;
        *${jupyter_pytorch_notebook_id}-*)
            notebook_id="${accelerator_flavor:+$accelerator_flavor/}${jupyter_pytorch_notebook_id}"
            ;;
        *)
            printf '%s\n' "No matching condition found for ${notebook_workload_name}."
            exit 1
            ;;
    esac

    _create_test_versions_source_of_truth "${notebook_id}"

    "${kbin}" exec "${notebook_workload_name}" -- /bin/sh -c "python3 -m pip install papermill"

    if _image_derived_from_datascience "${notebook_id}" ; then
        _test_datascience_notebook
    fi

    if [ -n "${notebook_id}" ] && ! [ "${notebook_id}" = "${jupyter_datascience_notebook_id}" ]; then
        _run_test "${notebook_id}"
    fi
}

test_target="${1:-}"

# Hard-coded list of supported "notebook_id" values - based on notebooks/ repo Makefile
jupyter_minimal_notebook_id='minimal'
jupyter_datascience_notebook_id='datascience'
jupyter_trustyai_notebook_id='trustyai'
jupyter_pytorch_notebook_id='pytorch'
jupyter_tensorflow_notebook_id='tensorflow'

notebook_name=$( _get_notebook_name "${test_target}" )
python_flavor="python-${test_target//*-python-/}"  # <-- python-3.11
os_flavor=$(_get_os_flavor "${test_target}")
accelerator_flavor=$(_get_accelerator_flavor "${test_target}")

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

printf '%s\n' "Waiting for ${notebook_name} workload to be ready.  This could take a few minutes..."
_wait_for_workload "${notebook_name}"

notebook_workload_name=$("${kbin}" get pods -l app="${notebook_name}" -o jsonpath='{.items[0].metadata.name}')

_handle_test

