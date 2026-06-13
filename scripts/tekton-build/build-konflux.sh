#!/usr/bin/env bash
# Run Konflux-aligned container builds locally/GHA from .tekton PipelineRun params.
#
# Native platform (linux/amd64 on amd64 runner, linux/arm64 on arm64 runner):
#   konflux-build-cli image build — same entrypoint as Konflux buildah-remote-oci-ta.
#
# Cross-arch on GHA (linux/ppc64le, linux/s390x via QEMU on amd64):
#   podman build --platform with the same hermetic cachi2 mounts and build-args as
#   Konflux. konflux-build-cli has no --platform flag; MPC uses native workers instead.
#
# Required env (usually set by tekton_build.py):
#   SOURCE_DIR      - repo root
#   IMAGE_TAG       - output image reference
#   DOCKERFILE      - path relative to SOURCE_DIR (e.g. jupyter/.../Dockerfile.cuda)
#   CONTEXT         - build context relative to SOURCE_DIR (usually .)
#   BUILD_ARGS_FILE - path relative to SOURCE_DIR (e.g. build-args/global.conf)
#
# Optional env:
#   BUILD_ARGS      - space-separated KEY=VAL inline build-args (Tekton build-args param)
#   BUILD_PLATFORM  - podman platform (e.g. linux/amd64, linux/ppc64le)
#   YUM_REPOS_D_SOURCES - container path(s) for --yum-repos-d-sources (konflux-build-cli only)
#   HERMETIC        - true|false (default: true)
#   IMAGE_SOURCE    - org.opencontainers.image.source (default: git remote origin URL)
#   IMAGE_REVISION  - git commit SHA (default: HEAD)
#   RHSM_KEY_DIR    - dir with org + activationkey files
#   CONTAINER_ENGINE - podman (default) or docker
#   LOG_LEVEL       - konflux-build-cli log level (default: info)
#   FORCE_PODMAN_BUILD - if 1, use podman build directly even on native (debug)
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=konflux-versions.env
source "$SCRIPT_DIR/konflux-versions.env"

: "${SOURCE_DIR:?SOURCE_DIR is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${DOCKERFILE:?DOCKERFILE is required}"
: "${CONTEXT:=.}"
: "${BUILD_ARGS_FILE:=}"
: "${HERMETIC:=true}"
: "${CONTAINER_ENGINE:=podman}"
: "${LOG_LEVEL:=info}"

SOURCE_DIR=$(cd "$SOURCE_DIR" && pwd)
CACHI2_DIR="$SOURCE_DIR/cachi2"

host_platform() {
  case "$(uname -m)" in
    x86_64) echo linux/amd64 ;;
    aarch64|arm64) echo linux/arm64 ;;
    ppc64le) echo linux/ppc64le ;;
    s390x) echo linux/s390x ;;
    *) echo "linux/$(uname -m)" ;;
  esac
}

platform_rpm_arch() {
  local arch="${1#linux/}"
  case "$arch" in
    amd64) echo x86_64 ;;
    arm64) echo aarch64 ;;
    *) echo "$arch" ;;
  esac
}

HOST_PLATFORM=$(host_platform)
BUILD_PLATFORM="${BUILD_PLATFORM:-$HOST_PLATFORM}"
CROSS_ARCH=false
if [[ "$BUILD_PLATFORM" != "$HOST_PLATFORM" ]]; then
  CROSS_ARCH=true
fi

USE_REMOTE_PODMAN=false
if [[ -n "${CONTAINER_HOST:-}" ]]; then
  USE_REMOTE_PODMAN=true
elif [[ -S "/var/run/podman/podman.sock" ]]; then
  USE_REMOTE_PODMAN=true
  CONTAINER_HOST="unix:///var/run/podman/podman.sock"
fi

BUILD_STORAGE=""
cleanup() {
  if [[ -n "$BUILD_STORAGE" ]]; then
    rm -rf "$BUILD_STORAGE" 2>/dev/null || sudo rm -rf "$BUILD_STORAGE" || true
  fi
}
if [[ "$USE_REMOTE_PODMAN" == "false" ]]; then
  BUILD_STORAGE=$(mktemp -d)
  trap cleanup EXIT
fi

if [[ "$HERMETIC" == "true" && ! -d "$CACHI2_DIR/output" ]]; then
  echo "Hermetic build requires cachi2/output. Run prefetch first." >&2
  exit 1
fi

if [[ -z "${IMAGE_SOURCE:-}" ]]; then
  IMAGE_SOURCE=$(git -C "$SOURCE_DIR" remote get-url origin 2>/dev/null || echo "unknown")
fi
if [[ -z "${IMAGE_REVISION:-}" ]]; then
  IMAGE_REVISION=$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
fi

podman_build_args_flags() {
  BUILD_ARGS_PODMAN=()
  if [[ -n "$BUILD_ARGS_FILE" ]]; then
    BUILD_ARGS_PODMAN+=(--build-arg-file "$BUILD_ARGS_FILE")
  fi
  if [[ -n "${BUILD_ARGS:-}" ]]; then
    # shellcheck disable=SC2206
    for arg in ${BUILD_ARGS}; do
      BUILD_ARGS_PODMAN+=(--build-arg "$arg")
    done
  fi
}

podman_hermetic_volume_flags() {
  HERMETIC_VOLUMES=()
  if [[ "$HERMETIC" != "true" ]]; then
    return
  fi
  HERMETIC_VOLUMES+=(-v "$CACHI2_DIR/output:/cachi2/output:Z")
  local rpm_arch rpm_repos
  rpm_arch=$(platform_rpm_arch "$BUILD_PLATFORM")
  rpm_repos="$CACHI2_DIR/output/deps/rpm/${rpm_arch}/repos.d"
  if [[ -d "$rpm_repos" ]]; then
    HERMETIC_VOLUMES+=(-v "$rpm_repos:/etc/yum.repos.d/:Z")
  fi
}

podman_platform_extra_flags() {
  PLATFORM_EXTRA=()
  if [[ "$BUILD_PLATFORM" == "linux/s390x" ]]; then
    # pyzmq/QEMU: CACHELINE_SIZE probe is undefined under qemu-user.
    PLATFORM_EXTRA+=(
      --env=CFLAGS=-Dundefined=64
      --env=CXXFLAGS=-Dundefined=64
      --unsetenv=CFLAGS
      --unsetenv=CXXFLAGS
    )
  fi
}

qemu_binfmt_enabled() {
  local arch="${BUILD_PLATFORM#linux/}"
  local handler="/proc/sys/fs/binfmt_misc/qemu-${arch}"
  [[ -r "$handler" ]] && grep -q '^enabled$' "$handler"
}

verify_qemu_execution() {
  local expected="${BUILD_PLATFORM#linux/}"
  local got
  got=$("$CONTAINER_ENGINE" run --rm --platform "$BUILD_PLATFORM" \
    registry.access.redhat.com/ubi9/ubi:latest uname -m)
  [[ "$got" == "$expected" ]]
}

ensure_qemu_binfmt() {
  local arch="${BUILD_PLATFORM#linux/}"
  if qemu_binfmt_enabled; then
    echo "QEMU binfmt handler for ${arch} is enabled"
    return 0
  fi
  if [[ -r /proc/sys/fs/binfmt_misc/status ]]; then
    echo "Registering QEMU binfmt for ${arch}..."
    "$CONTAINER_ENGINE" run --rm --privileged docker.io/tonistiigi/binfmt --install "$arch"
    if ! qemu_binfmt_enabled; then
      echo "QEMU binfmt for ${arch} is not enabled after registration" >&2
      exit 1
    fi
    return 0
  fi
  # Podman Machine (macOS/Windows): binfmt is inside the VM, not on the host OS.
  echo "No host binfmt_misc; verifying ${BUILD_PLATFORM} execution via podman..."
  if verify_qemu_execution; then
    echo "QEMU execution verified for ${BUILD_PLATFORM}"
    return 0
  fi
  echo "Cannot execute ${BUILD_PLATFORM} containers (QEMU not available)" >&2
  exit 1
}

run_cross_arch_podman_build() {
  ensure_qemu_binfmt
  podman_build_args_flags
  podman_hermetic_volume_flags
  podman_platform_extra_flags

  echo "--- Cross-arch podman build (QEMU): $BUILD_PLATFORM on $HOST_PLATFORM ---"
  echo "Output:      $IMAGE_TAG"
  echo "Dockerfile:  $DOCKERFILE"
  echo "Context:     $CONTEXT"
  echo "Hermetic:    $HERMETIC"
  echo "Build args:  ${BUILD_ARGS:-}"

  (
    cd "$SOURCE_DIR"
    "$CONTAINER_ENGINE" build \
      --platform "$BUILD_PLATFORM" \
      --ignorefile "$SCRIPT_DIR/cross-arch.dockerignore" \
      "${PLATFORM_EXTRA[@]}" \
      "${HERMETIC_VOLUMES[@]}" \
      "${BUILD_ARGS_PODMAN[@]}" \
      --label "org.opencontainers.image.source=${IMAGE_SOURCE}" \
      --label "org.opencontainers.image.revision=${IMAGE_REVISION}" \
      -f "$DOCKERFILE" \
      -t "$IMAGE_TAG" \
      "$CONTEXT"
  )
}

run_konflux_build_cli() {
  BUILD_ARGS_FLAGS=()
  if [[ -n "${BUILD_ARGS:-}" ]]; then
    # shellcheck disable=SC2206
    for arg in ${BUILD_ARGS}; do
      BUILD_ARGS_FLAGS+=(--build-args "$arg")
    done
  fi

  PODMAN_ARGS=(
    --rm
    --privileged
    --user 0:0
    -v "$SOURCE_DIR:/source:z"
    -v "$CACHI2_DIR:/cachi2:z"
    -e "TMPDIR=/var/tmp"
  )

  if [[ -n "$BUILD_STORAGE" ]]; then
    PODMAN_ARGS+=(-v "$BUILD_STORAGE:/var/lib/containers/storage:z")
  fi

  CONTAINERS_CONF="$SOURCE_DIR/ci/cached-builds/containers.conf"
  if [[ -f "$CONTAINERS_CONF" ]]; then
    PODMAN_ARGS+=(
      -v "$CONTAINERS_CONF:/etc/containers/containers.conf:ro,z"
    )
  fi

  if [[ "$USE_REMOTE_PODMAN" == "true" ]]; then
    PODMAN_ARGS+=(
      -e "CONTAINER_HOST=${CONTAINER_HOST}"
      -v "/var/run/podman/podman.sock:/var/run/podman/podman.sock:z"
    )
  fi

  RHSM_ARGS=()
  if [[ -n "${RHSM_KEY_DIR:-}" && -f "$RHSM_KEY_DIR/org" && -f "$RHSM_KEY_DIR/activationkey" ]]; then
    PODMAN_ARGS+=(-v "$RHSM_KEY_DIR:/activation-key:ro,z")
    RHSM_ARGS+=(
      --rhsm-org /activation-key/org
      --rhsm-activation-key /activation-key/activationkey
      --rhsm-activation-mount /activation-key
    )
  fi

  KBC_ARGS=(
    image build
    -f "$DOCKERFILE"
    -t "$IMAGE_TAG"
    --source /source
    --context "$CONTEXT"
    --image-source "$IMAGE_SOURCE"
    --image-revision "$IMAGE_REVISION"
    --inherit-labels=true
    --add-legacy-labels
    --include-legacy-buildinfo-path=true
    --skip-injections=false
    --skip-unused-stages=true
    --ulimits nofile=4096:4096
    --security-opts unmask=/proc/interrupts
    --no-cache
    --src-tls-verify=true
    --dest-tls-verify=true
  )

  if [[ -n "$BUILD_ARGS_FILE" ]]; then
    KBC_ARGS+=(--build-args-file "/source/$BUILD_ARGS_FILE")
  fi

  if [[ "$HERMETIC" == "true" ]]; then
    KBC_ARGS+=(
      --hermetic
      --prefetch-dir /cachi2
      --prefetch-env-mount /cachi2/cachi2.env
      --prefetch-output-mount /cachi2/output
      --yum-repos-d-target /etc/yum.repos.d
    )
    if [[ -n "${YUM_REPOS_D_SOURCES:-}" ]]; then
      # shellcheck disable=SC2206
      for repos_dir in ${YUM_REPOS_D_SOURCES}; do
        KBC_ARGS+=(--yum-repos-d-sources "$repos_dir")
      done
    fi
    if [[ -d "$SOURCE_DIR/repos.d" ]]; then
      KBC_ARGS+=(--yum-repos-d-sources "/source/repos.d")
    fi
  fi

  echo "--- Konflux build-images (konflux-build-cli) ---"
  echo "Image:       $KONFLUX_BUILD_CLI_IMAGE"
  echo "Output:      $IMAGE_TAG"
  echo "Dockerfile:  $DOCKERFILE"
  echo "Context:     $CONTEXT"
  echo "Platform:    $BUILD_PLATFORM (native on $HOST_PLATFORM)"
  echo "Hermetic:    $HERMETIC"
  echo "Remote:      ${USE_REMOTE_PODMAN} (${CONTAINER_HOST:-local storage})"
  echo "Yum repos:   ${YUM_REPOS_D_SOURCES:-}"
  echo "Build args:  ${BUILD_ARGS:-}"

  "$CONTAINER_ENGINE" run "${PODMAN_ARGS[@]}" \
    --entrypoint konflux-build-cli \
    "$KONFLUX_BUILD_CLI_IMAGE" \
    --loglevel "$LOG_LEVEL" \
    "${KBC_ARGS[@]}" \
    "${BUILD_ARGS_FLAGS[@]}" \
    ${RHSM_ARGS[@]+"${RHSM_ARGS[@]}"}
}

if [[ "$CROSS_ARCH" == "true" || "${FORCE_PODMAN_BUILD:-}" == "1" ]]; then
  if [[ "$CROSS_ARCH" == "true" ]]; then
    run_cross_arch_podman_build
  else
    BUILD_PLATFORM="$HOST_PLATFORM"
    run_cross_arch_podman_build
  fi
else
  run_konflux_build_cli
fi

echo "Build complete: $IMAGE_TAG"
