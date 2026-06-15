#!/usr/bin/env bash
# Run Konflux prefetch-dependencies locally/GHA using the same hermeto image and
# konflux-build-cli entrypoint as task-prefetch-dependencies-oci-ta:0.3.
#
# Usage:
#   INPUT_JSON='[{"path":"prefetch-input/odh","type":"rpm"},...]' \
#     ./scripts/tekton-build/prefetch-hermeto.sh
#
# Optional env:
#   HERMETO_IMAGE            - override image (default from konflux-versions.env)
#   SOURCE_DIR               - repo root (default: cwd)
#   OUTPUT_DIR               - cachi2 output dir relative to SOURCE_DIR (default: cachi2/output)
#   CONFIG_FILE              - hermeto config yaml (default: scripts/tekton-build/hermeto-config.yaml)
#   RHSM_KEY_DIR             - dir with `org` and `activationkey` files for RHEL RPM prefetch
#   ENABLE_PACKAGE_REGISTRY_PROXY - default false (no in-cluster proxy outside Konflux)
#   CONTAINER_ENGINE         - podman (default) or docker
#
# Pip lockfiles must declare --index-url (e.g. RHOAI). Hermeto reads it from the
# requirements file, same as Konflux prefetch-dependencies (see Hermeto pip docs).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=konflux-versions.env
source "$SCRIPT_DIR/konflux-versions.env"

SOURCE_DIR="${SOURCE_DIR:-.}"
OUTPUT_DIR="${OUTPUT_DIR:-cachi2/output}"
CONFIG_FILE="${CONFIG_FILE:-scripts/tekton-build/hermeto-config.yaml}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-podman}"
# Konflux task-prefetch-dependencies-oci-ta:0.3 default (params.log-level).
LOG_LEVEL="${LOG_LEVEL:-debug}"
SBOM_TYPE="${SBOM_TYPE:-spdx}"
MODE="${MODE:-strict}"
ENABLE_PACKAGE_REGISTRY_PROXY="${ENABLE_PACKAGE_REGISTRY_PROXY:-false}"

if [[ -z "${INPUT_JSON:-}" ]]; then
  echo "No prefetch-input provided; skipping prefetch." >&2
  exit 0
fi

SOURCE_DIR=$(cd "$SOURCE_DIR" && pwd)
CONFIG_PATH="$SOURCE_DIR/$CONFIG_FILE"
CACHI2_DIR="$SOURCE_DIR/cachi2"
OUTPUT_PATH="$SOURCE_DIR/$OUTPUT_DIR"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Hermeto config not found: $CONFIG_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_PATH"
CONFIG_RUNTIME="$CACHI2_DIR/hermeto-config.yaml"
cp "$CONFIG_PATH" "$CONFIG_RUNTIME"

PODMAN_ARGS=(
  --rm
  -v "$SOURCE_DIR:/source:z"
  -v "$CACHI2_DIR:/cachi2:z"
  -v "$CONFIG_RUNTIME:/mnt/config/config.yaml:z"
)

RHSM_ARGS=()
if [[ -n "${RHSM_KEY_DIR:-}" && -f "$RHSM_KEY_DIR/org" && -f "$RHSM_KEY_DIR/activationkey" ]]; then
  PODMAN_ARGS+=(-v "$RHSM_KEY_DIR:/activation-key:ro,z")
  RHSM_ARGS+=(--rhsm-org /activation-key/org --rhsm-activation-key /activation-key/activationkey)
fi

echo "--- Konflux prefetch-dependencies (konflux-build-cli) ---"
echo "Image:  $HERMETO_IMAGE"
echo "Source: $SOURCE_DIR"
echo "Output: $OUTPUT_PATH"
echo "Input:  $INPUT_JSON"

"$CONTAINER_ENGINE" run "${PODMAN_ARGS[@]}" \
  --entrypoint konflux-build-cli \
  "$HERMETO_IMAGE" \
  --loglevel "$LOG_LEVEL" \
  prefetch-dependencies \
  --input "$INPUT_JSON" \
  --source-dir /source \
  --output-dir /cachi2/output \
  --config-file /mnt/config/config.yaml \
  --sbom-format "$SBOM_TYPE" \
  --mode "$MODE" \
  --output-dir-mount-point /cachi2/output \
  --env-files /cachi2/cachi2.env \
  --env-files /cachi2/prefetch.env \
  --env-files /cachi2/prefetch-env.json \
  --enable-package-registry-proxy="$ENABLE_PACKAGE_REGISTRY_PROXY" \
  ${RHSM_ARGS[@]+"${RHSM_ARGS[@]}"}

# konflux-build-cli runs as root in the container; fix ownership for later host steps (GHA).
if ! test -w "$OUTPUT_PATH" 2>/dev/null; then
  sudo chown -R "$(id -u):$(id -g)" "$CACHI2_DIR" 2>/dev/null || true
fi

echo "Prefetch complete: $OUTPUT_PATH"
