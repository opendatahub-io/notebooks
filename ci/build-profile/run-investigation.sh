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
  rg 'BUILD_PROFILE_' "${log}" || true
  return "${status}"
}

arbitrary_uid_smoke() {
  local image="$1"
  local name="$2"
  # OpenShift uses large UIDs (e.g. 1000880000) but rootless podman on GHA/mac only
  # allows subuid-mapped IDs. Match tests/containers (jupyterlab uses 4321 + gid 0).
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
        "--build-arg FIXUP_MODE=${mode}"
      img="${IMAGE_REGISTRY}:minimal-user1001-${mode}-${IMAGE_TAG}"
      arbitrary_uid_smoke "${img}" "minimal-user1001-${mode}" || true
    done
    img="${IMAGE_REGISTRY}:minimal-timing-${IMAGE_TAG}"
    if ${CONTAINER_ENGINE} image exists "${img}" >/dev/null 2>&1; then
      arbitrary_uid_smoke "${img}" "minimal-timing" || true
    fi
    if [[ "${EXPERIMENT}" == "all" ]]; then
      img="${IMAGE_REGISTRY}:minimal-timing-${IMAGE_TAG}"
      if ${CONTAINER_ENGINE} image exists "${img}" >/dev/null 2>&1; then
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
    # Re-prefetch so pip wheels match pytorch requirements (not minimal's).
    prefetch_component jupyter/pytorch/ubi9-python-3.12 cuda
    profile_build pytorch-perm \
      ci/build-profile/dockerfiles/pytorch-perm.Dockerfile.cuda \
      jupyter/pytorch/ubi9-python-3.12/build-args/cuda.conf || true
    ;;
esac

echo "=== Investigation complete; logs in ${BUILD_LOG_DIR} ==="
