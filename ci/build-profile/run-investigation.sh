#!/usr/bin/env bash
# Run build-profile investigations (#3928). Intended for GHA and local cold builds.
set -Eeuo pipefail

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
  local component_dir="$1"
  local prefetch_dir
  if [[ -d "${component_dir}/prefetch-input" ]]; then
    prefetch_dir="${component_dir}/prefetch-input"
  elif grep -q 'prefetch-input/' "${component_dir}"/Dockerfile* 2>/dev/null && [[ -d prefetch-input ]]; then
    prefetch_dir="prefetch-input"
  else
    prefetch_dir=""
  fi
  if [[ -n "${prefetch_dir}" && -d cachi2/output ]]; then
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
  volumes=$(cachi2_volumes "$(dirname "${dockerfile}")")

  local build_args=()
  if [[ -f "${conf}" ]]; then
    while IFS= read -r line; do
      [[ "${line}" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line// }" ]] && continue
      build_args+=(--build-arg "${line}")
    done < "${conf}"
  fi

  echo "=== Build ${name} -> ${tag} ==="
  local start end elapsed
  start=$(date +%s)
  # shellcheck disable=SC2086
  "${ROOT_DIR}/scripts/sandbox.py" --dockerfile "${dockerfile}" --platform "${PLATFORM}" -- \
    ${CONTAINER_ENGINE} build --no-cache ${volumes} --platform="${PLATFORM}" \
    --tag "${tag}" --file "${dockerfile}" ${build_args[@]} ${extra_args} {} \
    2>&1 | tee "${log}"
  end=$(date +%s)
  elapsed=$((end - start))
  echo "BUILD_PROFILE_TOTAL ${name} ${elapsed}"
  echo "::notice title=build-profile::total ${name} elapsed=${elapsed}s"
  rg 'BUILD_PROFILE_' "${log}" || true
}

arbitrary_uid_smoke() {
  local image="$1"
  local name="$2"
  echo "=== Arbitrary UID smoke: ${name} ==="
  if ${CONTAINER_ENGINE} run --rm --user 1000880000:0 --entrypoint="" "${image}" \
    bash -c 'touch /opt/app-root/src/.write-test && rm /opt/app-root/src/.write-test && echo BUILD_PROFILE_ARBITRARY_UID_OK'; then
    echo "BUILD_PROFILE_ARBITRARY_UID ${name} ok"
  else
    echo "BUILD_PROFILE_ARBITRARY_UID ${name} FAILED" >&2
    return 1
  fi
}

run_container_tests() {
  local image="$1"
  echo "=== Container tests for ${image} ==="
  uv run pytest tests/containers \
    --image="${image}" \
    -m "not openshift and not cuda and not rocm" \
    --maxfail=3 -q
}

case "${EXPERIMENT}" in
  minimal-timing|all)
    prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    profile_build minimal-timing \
      ci/build-profile/dockerfiles/minimal-timing.Dockerfile.cpu \
      jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf
    ;;
esac

case "${EXPERIMENT}" in
  minimal-user1001|all)
    if [[ "${EXPERIMENT}" == "minimal-user1001" ]]; then
      prefetch_component jupyter/minimal/ubi9-python-3.12 cpu
    fi
    for mode in none full; do
      profile_build "minimal-user1001-${mode}" \
        ci/build-profile/dockerfiles/minimal-user1001.Dockerfile.cpu \
        jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf \
        "--build-arg FIXUP_MODE=${mode}"
      img="${IMAGE_REGISTRY}:minimal-user1001-${mode}-${IMAGE_TAG}"
      arbitrary_uid_smoke "${img}" "minimal-user1001-${mode}" || true
    done
    if [[ "${EXPERIMENT}" == "all" ]]; then
      img="${IMAGE_REGISTRY}:minimal-user1001-none-${IMAGE_TAG}"
      run_container_tests "${img}" || true
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
      "--build-arg RPM_ARCH=${RPM_ARCH}"
    ;;
esac

case "${EXPERIMENT}" in
  pytorch-perm|all)
    prefetch_component jupyter/pytorch/ubi9-python-3.12 cuda
    profile_build pytorch-perm \
      ci/build-profile/dockerfiles/pytorch-perm.Dockerfile.cuda \
      jupyter/pytorch/ubi9-python-3.12/build-args/cuda.conf
    ;;
esac

echo "=== Investigation complete; logs in ${BUILD_LOG_DIR} ==="
