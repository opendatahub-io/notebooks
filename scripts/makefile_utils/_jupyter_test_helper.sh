#! /usr/bin/env bash

## Description:
##
## This script is intended to be invoked via the Makefile test-% target of the notebooks repository and assumes the deploy-% target
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
##    - kubectl:    https://kubernetes.io/docs/reference/kubectl/
##      - a local copy of kubectl is downloaded via the Makefile bin/kubectl target, and stored in bin/kubectl within the notebooks repo
##    - yq:         https://mikefarah.gitbook.io/yq
##      - a local copy of yq is downloaded via the Makefile bin/yq target, and stored in bin/yq within the notebooks repo
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

# Description:
#   Computes the absolute path of the imagestream manifest for the jupyter workbench image under test
#
# Input:
#   $workbench_scope
#
# Returns:
#   Absolute path to the iamgestream manifest file corresponding to the notebook under test
function _get_jupyter_imagestream_source_of_truth_filepath()
{
    # shellcheck disable=SC2154
    local manifest_directory="${root_repo_directory}/manifests"
    local imagestream_directory="${manifest_directory}/base"

    local file_suffix='notebook-imagestream.yaml'
    local filename=
    # shellcheck disable=SC2154
    case "${workbench_scope}" in
        "$jupyter_minimal_workbench_id")
            filename="jupyter-${workbench_accelerator:+"$workbench_accelerator"-}${workbench_scope}-${file_suffix}"
            if [ "${workbench_accelerator}" = 'cuda' ]; then
                filename="jupyter-${workbench_scope}-gpu-${file_suffix}"
            fi
            ;;
        "$jupyter_datascience_workbench_id" | "$jupyter_trustyai_workbench_id")
            filename="jupyter-${workbench_scope}-${file_suffix}"
            ;;
        "$jupyter_pytorch_workbench_id" | "$jupyter_tensorflow_workbench_id")
            filename="jupyter-${workbench_accelerator:+"$workbench_accelerator"-}${workbench_scope}-${file_suffix}"
            if [ "${workbench_accelerator}" = 'cuda' ]; then
                filename="jupyter-${workbench_scope}-${file_suffix}"
            fi
            ;;
    esac

    local filepath="${imagestream_directory}/${filename}"

    if ! [ -e "${filepath}" ]; then
        printf '%s\n' "Unable to determine imagestream manifest.  Computed filepath '${filepath}' does not exist."
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
function _create_jupyter_workbench_test_versions_source_of_truth()
{
    local version_filename='expected_versions.json'

    local test_version_truth_filepath=
    test_version_truth_filepath="$( _get_jupyter_imagestream_source_of_truth_filepath )"

    local nbdime_version='4.0'
    local nbgitpuller_version='1.2'

    # shellcheck disable=SC2154
    expected_versions=$("${yqbin}" '.spec.tags[0].annotations | .["opendatahub.io/notebook-software"] + .["opendatahub.io/notebook-python-dependencies"]' "${test_version_truth_filepath}" |
        "${yqbin}" -N -p json -o yaml |
        nbdime_version=${nbdime_version} nbgitpuller_version=${nbgitpuller_version} "${yqbin}" '. + [{"name": "nbdime", "version": strenv(nbdime_version)},{"name": "nbgitpuller", "version": strenv(nbgitpuller_version)}]' |
        "${yqbin}" -N -o json '[ .[] | (.name | key) = "key" | (.version | key) = "value" ] | from_entries')

    # Following disabled shellcheck intentional as the intended behavior is for those ${1}, ${2} variables to only be expanded when running within kubernetes
    # shellcheck disable=SC2016
    # shellcheck disable=SC2154
    "${kbin}" exec "${workload_name}" -- /bin/sh -c 'touch "${1}"; printf "%s\n" "${2}" > "${1}"' -- "${version_filename}" "${expected_versions}"
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
function _run_jupyter_papermill_test()
{
    local test_notebook_file='test_notebook.ipynb'
    # shellcheck disable=SC2154
    local repo_test_directory="${root_repo_directory}/${workbench_directory}/test"
    # shellcheck disable=SC2154
    local output_file_prefix="${workbench_scope}_${workbench_os}"

    # shellcheck disable=SC2154
    "${kbin}" cp "${repo_test_directory}/${test_notebook_file}" "${workload_name}:./${test_notebook_file}"

    # shellcheck disable=SC2154
    local workbench_name="${workbench_feature} ${workbench_scope} ${workbench_os} workbench"

	if ! "${kbin}" exec "${workload_name}" -- /bin/sh -c "export IPY_KERNEL_LOG_LEVEL=DEBUG; python3 -m papermill ${test_notebook_file} ${output_file_prefix}_output.ipynb --kernel python3 --log-level DEBUG --stderr-file ${output_file_prefix}_error.txt" ; then
		# shellcheck disable=SC2154
		printf '%s\n' "ERROR: The ${workbench_name} encountered a failure. To investigate the issue, you can review the logs located in the ocp-ci cluster on 'artifacts/notebooks-e2e-tests/jupyter-${workbench_scope}-${workbench_os}-${workbench_python}-test-e2e' directory or run 'cat ${output_file_prefix}_error.txt' within your container."
		exit 1
	fi

    local rc=
    set +e
    local test_result=
    test_result=$("${kbin}" exec "${workload_name}" -- /bin/sh -c "grep FAILED ${output_file_prefix}_error.txt" 2>&1)
    rc=$?
    set -e

    case "${rc}" in
        0)
            printf '\n\n%s\n' "ERROR: The ${workbench_name} encountered a test failure. The make process has been aborted."
            "${kbin}" exec "${workload_name}" -- /bin/sh -c "cat ${output_file_prefix}_error.txt"
            exit 1
            ;;
        1)
            printf '\n%s\n\n' "The ${workbench_name} tests ran successfully"
            ;;
        2)
            printf '\n\n%s\n' "ERROR: The ${workbench_name} encountered an unexpected failure. The make process has been aborted."
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
function _jupyter_workbench_derived_from_datascience()
{
    local datascience_derived_images=("${jupyter_datascience_workbench_id}" "${jupyter_trustyai_workbench_id}" "${jupyter_tensorflow_workbench_id}" "${jupyter_pytorch_workbench_id}")

    printf '%s\0' "${datascience_derived_images[@]}" | grep -Fz -- "${workbench_scope}"
}

# Description:
#	Convenience function that will invoke the minimal and datascience papermill tests against the running notebook workload
function _test_jupyter_datascience_workbench()
{
    _run_jupyter_papermill_test "${jupyter_minimal_workbench_id}"
    _run_jupyter_papermill_test "${jupyter_datascience_workbench_id}"
}


# Hard-coded list of supported "notebook_id" values - based on notebooks/ repo Makefile
jupyter_minimal_workbench_id='minimal'
jupyter_datascience_workbench_id='datascience'
jupyter_trustyai_workbench_id='trustyai'
jupyter_pytorch_workbench_id='pytorch'
jupyter_tensorflow_workbench_id='tensorflow'
