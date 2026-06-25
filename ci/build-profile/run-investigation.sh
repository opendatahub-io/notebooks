#!/usr/bin/env bash
# Run build-profile investigations (#3928). Intended for GHA and local cold builds.
set -Euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EXPERIMENT="${1:-all}"
PLATFORM="${BUILD_ARCH:-linux/amd64}"
RPM_ARCH="${RPM_ARCH:-x86_64}"
IMAGE_TAG="${IMAGE_TAG:-profile-investigate}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-localhost/notebooks-profile}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-podman}"
BUILD_LOG_DIR="${BUILD_LOG_DIR:-${RUNNER_TEMP:-/tmp}/build-profile-logs}"
mkdir -p "${BUILD_LOG_DIR}"

read_conf() {
  local conf="$1"
  local key="$2"
  awk -F= -v k="${key}" '$1 == k { print $2; exit }' "${conf}"
}

cachi2_volumes() {
  if [[ -d cachi2/output/deps/rpm/${RPM_ARCH}/repos.d ]]; then
    echo \
      --volume "${ROOT_DIR}/cachi2/output:/cachi2/output:Z" \
      --volume "${ROOT_DIR}/cachi2/output/deps/rpm/${RPM_ARCH}/repos.d/:/etc/yum.repos.d/:Z"
  fi
}

prefetch_component() {
  local component_dir="$1"
  local flavor="$2"
  echo "=== Prefetch ${component_dir} flavor=${flavor} ==="
  scripts/lockfile-generators/prefetch-all.sh --component-dir "${component_dir}" --flavor "${flavor}"
}

profile_build() {
  local name="$1"
  local dockerfile="$2"
  local conf="$3"
  local extra_args="${4:-}"
  local tag="${IMAGE_REGISTRY}:${name}-${IMAGE_TAG}"
  local log="${BUILD_LOG_DIR}/${name}.log"
  local volumes
  volumes=$(cachi2_volumes)

  local build_args=()
  if [[ -f "${conf}" ]]; then
    while IFS= read -r line; do
      [[ "${line}" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line// }" ]] && continue
      build_args+=(--build-arg "${line}")
    done < "${conf}"
  fi

  echo "=== Build ${name} -> ${tag} ==="
  local start end elapsed status=0
  start=$(date +%s)
  # shellcheck disable=SC2086
  uv run "${ROOT_DIR}/scripts/sandbox.py" --dockerfile "${dockerfile}" --platform "${PLATFORM}" -- \
    ${CONTAINER_ENGINE} build --no-cache ${volumes} --platform="${PLATFORM}" \
    --tag "${tag}" --file "${dockerfile}" ${build_args[@]} ${extra_args} '{};' \
    2>&1 | tee "${log}" || status=$?
  end=$(date +%s)
  elapsed=$((end - start))
  echo "BUILD_PROFILE_TOTAL ${name} ${elapsed} exit=${status}"
  echo "::notice title=build-profile::total ${name} elapsed=${elapsed}s exit=${status}"
  rg 'BUILD_PROFILE_|PREPARE_GROUP_WRITABLE_WHEELS' "${log}" || true
  return "${status}"
}

arbitrary_uid_smoke() {
  local image="$1"
  local name="$2"
  local uid="${ARBITRARY_UID_SMOKE:-4321}"
  echo "=== Arbitrary UID smoke: ${name} (uid=${uid}:0) ==="
  if ${CONTAINER_ENGINE} run --rm --user "${uid}:0" --entrypoint="" "${image}" \
    bash -c 'touch "${HOME}/.write-test" && rm "${HOME}/.write-test" && echo BUILD_PROFILE_ARBITRARY_UID_OK'; then
    echo "BUILD_PROFILE_ARBITRARY_UID ${name} ok"
  else
    echo "BUILD_PROFILE_ARBITRARY_UID ${name} FAILED" >&2
    return 1
  fi
}

pip_install_smoke() {
  local image="$1"
  local name="$2"
  local uid="${PIP_INSTALL_UID:-23456}"
  echo "=== Pip install smoke: ${name} (uid=${uid}:0) ==="
  if ${CONTAINER_ENGINE} run --rm --user "${uid}:0" --entrypoint="" "${image}" \
    python3 -m pip install cowsay; then
    echo "BUILD_PROFILE_PIP_INSTALL ${name} ok"
  else
    echo "BUILD_PROFILE_PIP_INSTALL ${name} FAILED" >&2
    return 1
  fi
}

mode_analysis_in_image() {
  local image="$1"
  local name="$2"
  echo "=== Mode analysis in ${name} ==="
  ${CONTAINER_ENGINE} run --rm --entrypoint="" "${image}" \
    /usr/local/bin/analyze-site-package-modes.sh /opt/app-root/lib/python3.12/site-packages \
    2>&1 | tee -a "${BUILD_LOG_DIR}/${name}-modes.log" || true
}

run_container_tests() {
  local image="$1"
  local extra_mark="${2:-}"
  echo "=== Container tests for ${image} ==="
  local mark="not openshift and not cuda and not rocm"
  if [[ -n "${extra_mark}" ]]; then
    mark="${mark} and ${extra_mark}"
  fi
  uv run pytest tests/containers \
    --image="${image}" \
    -m "${mark}" \
    --maxfail=3 -q
}

run_pip_test() {
  local image="$1"
  echo "=== pytest pip install for ${image} ==="
  uv run pytest tests/containers/base_image_test.py::TestBaseImage::test_pip_install_cowsay_runs \
    --image="${image}" -q
}

case "${EXPERIMENT}" in
  minimal-timing|all)
    prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    profile_build minimal-timing \
      ci/build-profile/dockerfiles/minimal-timing.Dockerfile.cpu \
      jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf || true
    ;;
esac

case "${EXPERIMENT}" in
  minimal-user1001|all)
    if [[ "${EXPERIMENT}" == "minimal-user1001" ]]; then
      prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    fi
    for mode in none chmod-only full; do
      profile_build "minimal-user1001-${mode}" \
        ci/build-profile/dockerfiles/minimal-user1001.Dockerfile.cpu \
        jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf \
        "--build-arg FIXUP_MODE=${mode}" || true
      img="${IMAGE_REGISTRY}:minimal-user1001-${mode}-${IMAGE_TAG}"
      if ${CONTAINER_ENGINE} image exists "${img}" >/dev/null 2>&1; then
        arbitrary_uid_smoke "${img}" "minimal-user1001-${mode}" || true
        if [[ "${mode}" == "none" ]]; then
          pip_install_smoke "${img}" "minimal-user1001-none" || true
          run_pip_test "${img}" || true
        fi
      fi
    done
    ;;
esac

case "${EXPERIMENT}" in
  minimal-umask002|all)
    if [[ "${EXPERIMENT}" == "minimal-umask002" ]]; then
      prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    fi
    profile_build minimal-umask002 \
      ci/build-profile/dockerfiles/minimal-umask002.Dockerfile.cpu \
      jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf || true
    ;;
esac

case "${EXPERIMENT}" in
  minimal-gw-wheels|all)
    if [[ "${EXPERIMENT}" == "minimal-gw-wheels" ]]; then
      prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    fi
    profile_build minimal-gw-wheels \
      ci/build-profile/dockerfiles/minimal-gw-wheels.Dockerfile.cpu \
      jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf || true
    img="${IMAGE_REGISTRY}:minimal-gw-wheels-${IMAGE_TAG}"
    if ${CONTAINER_ENGINE} image exists "${img}" >/dev/null 2>&1; then
      arbitrary_uid_smoke "${img}" "minimal-gw-wheels" || true
      pip_install_smoke "${img}" "minimal-gw-wheels" || true
      run_pip_test "${img}" || true
    fi
    ;;
esac

case "${EXPERIMENT}" in
  minimal-timing|minimal-user1001|all)
    img="${IMAGE_REGISTRY}:minimal-timing-${IMAGE_TAG}"
    if ${CONTAINER_ENGINE} image exists "${img}" >/dev/null 2>&1; then
      arbitrary_uid_smoke "${img}" "minimal-timing" || true
      if [[ "${EXPERIMENT}" == "all" ]]; then
        run_container_tests "${img}" || true
      fi
    fi
    ;;
esac

case "${EXPERIMENT}" in
  dnf-benchmark|all)
    if [[ "${EXPERIMENT}" == "dnf-benchmark" ]]; then
      prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    fi
    profile_build dnf-benchmark \
      ci/build-profile/dockerfiles/dnf-benchmark.Dockerfile.cpu \
      jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf \
      "--build-arg RPM_ARCH=${RPM_ARCH}" || true
    ;;
esac

case "${EXPERIMENT}" in
  pytorch-perm|all)
    prefetch_component jupyter/pytorch/ubi9-python-3.12 cuda
    profile_build pytorch-perm \
      ci/build-profile/dockerfiles/pytorch-perm.Dockerfile.cuda \
      jupyter/pytorch/ubi9-python-3.12/build-args/cuda.conf || true
    ;;
esac

echo "=== Investigation complete; logs in ${BUILD_LOG_DIR} ==="
