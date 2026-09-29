#!/usr/bin/env bash
set -Eeuo pipefail

# Run the offline JupyterLab browser suite without publishing a port or giving
# the browser access to a container runtime socket. The browser and workbench
# share only a unique internal container network.

ENGINE="${CONTAINER_ENGINE:-}"
if [[ -z "${ENGINE}" ]]; then
  if command -v podman >/dev/null 2>&1; then
    ENGINE=podman
  elif command -v docker >/dev/null 2>&1; then
    ENGINE=docker
  else
    echo "No podman or docker executable found" >&2
    exit 2
  fi
fi

BROWSER_IMAGE="${OFFLINE_BROWSER_IMAGE:-workbench-images-tests:latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
OFFLINE_SPEC_PATH="${SCRIPT_DIR}/../tests/jupyter-offline.spec.ts"
PLAYWRIGHT_CONFIG_PATH="${SCRIPT_DIR}/../playwright.config.ts"
OFFLINE_MODELS_PATH="${SCRIPT_DIR}/../tests/models/jupyterlab"
DEFAULT_JUPYTER_TEST_IMAGE="$(sed -n 's/^export const DEFAULT_JUPYTER_TEST_IMAGE = "\(.*\)";$/\1/p' "${PLAYWRIGHT_CONFIG_PATH}")"
[[ -n "${DEFAULT_JUPYTER_TEST_IMAGE}" ]] || {
  echo "Could not read DEFAULT_JUPYTER_TEST_IMAGE from ${PLAYWRIGHT_CONFIG_PATH}" >&2
  exit 2
}
WORKBENCH_IMAGE="${OFFLINE_WORKBENCH_IMAGE:-${DEFAULT_JUPYTER_TEST_IMAGE}}"
RESULTS_DIR="${OFFLINE_RESULTS_DIR:-${REPO_ROOT}/tests/browser/results/offline}"
STARTUP_TIMEOUT="${OFFLINE_STARTUP_TIMEOUT:-180}"
TEST_TIMEOUT="${OFFLINE_TEST_TIMEOUT:-900}"
FAKE_VALUE="${OFFLINE_FAKE_VALUE:-offline-browser-fixture}"
PLAYWRIGHT_ARGS=()
PLAYWRIGHT_ARGS+=(--project=chromium --grep @jupyter)
if [[ -n "${OFFLINE_PLAYWRIGHT_ARGS:-}" ]]; then
  OFFLINE_EXTRA_ARGS=()
  read -r -a OFFLINE_EXTRA_ARGS <<<"${OFFLINE_PLAYWRIGHT_ARGS}"
  for arg in "${OFFLINE_EXTRA_ARGS[@]}"; do
    case "${arg}" in
      --project|--project=*|--grep|--grep=*)
        echo "OFFLINE_PLAYWRIGHT_ARGS cannot override --project=chromium or --grep @jupyter: ${arg}" >&2
        exit 2
        ;;
    esac
  done
  PLAYWRIGHT_ARGS+=("${OFFLINE_EXTRA_ARGS[@]}")
fi
BASE_PATH="${OFFLINE_BASE_PATH:-/notebook/offline/}"
BASE_URL="http://workbench:8888${BASE_PATH}"
READINESS_URL="http://127.0.0.1:8888${BASE_PATH}"

mkdir -p "${RESULTS_DIR}"
printf 'running\n' >"${RESULTS_DIR}/runner.exit"
WORKBENCH_NAME="offline-jupyter-workbench-$$"
RUNNER_NAME="offline-jupyter-browser-$$"
NETWORK_NAME="offline-jupyter-network-$$"
workbench_started=0
runner_started=0
network_created=0

cleanup() {
  local primary_status=$?
  local cleanup_status=0
  trap - EXIT
  set +e
  # Names are unique to this invocation. Always inspect and remove them so a
  # failed create/start cannot leave an orphan behind.
  "${ENGINE}" logs "${RUNNER_NAME}" >"${RESULTS_DIR}/runner.log" 2>&1 || true
  "${ENGINE}" stop --time 5 "${RUNNER_NAME}" >>"${RESULTS_DIR}/runner-cleanup.log" 2>&1 || true
  "${ENGINE}" rm -f "${RUNNER_NAME}" >>"${RESULTS_DIR}/runner-cleanup.log" 2>&1 || cleanup_status=1
  "${ENGINE}" logs "${WORKBENCH_NAME}" >"${RESULTS_DIR}/workbench.log" 2>&1 || true
  "${ENGINE}" exec "${WORKBENCH_NAME}" bash -lc 'cat /opt/app-root/src/kale.log' >"${RESULTS_DIR}/kale.log" 2>&1 || true
  "${ENGINE}" stop --time 5 "${WORKBENCH_NAME}" >>"${RESULTS_DIR}/cleanup.log" 2>&1 || true
  "${ENGINE}" rm -f "${WORKBENCH_NAME}" >>"${RESULTS_DIR}/cleanup.log" 2>&1 || cleanup_status=1
  if [[ "${network_created}" == 1 ]]; then
    "${ENGINE}" network rm "${NETWORK_NAME}" >>"${RESULTS_DIR}/cleanup.log" 2>&1 || cleanup_status=1
  fi
  if (( primary_status == 0 && cleanup_status != 0 )); then
    primary_status=1
  fi
  printf '%s\n' "${primary_status}" >"${RESULTS_DIR}/runner.exit"
  exit "${primary_status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${ENGINE}" image inspect "${WORKBENCH_IMAGE}" >/dev/null 2>&1 || {
  echo "Workbench image is not available locally: ${WORKBENCH_IMAGE}" >&2
  echo "Pull or build it before running this offline suite." >&2
  exit 2
}
"${ENGINE}" image inspect "${BROWSER_IMAGE}" >/dev/null 2>&1 || {
  echo "Browser runner image is not available locally: ${BROWSER_IMAGE}" >&2
  echo "Build tests/browser/Dockerfile while online before running this suite." >&2
  exit 2
}

"${ENGINE}" network create --internal "${NETWORK_NAME}" >/dev/null
network_created=1

"${ENGINE}" run --pull=never --detach \
  --name "${WORKBENCH_NAME}" \
  --network "${NETWORK_NAME}" \
  --network-alias workbench \
  --user 12345:0 \
  --workdir /opt/app-root/src \
  --env HOME=/opt/app-root/src \
  --env NOTEBOOK_ROOT_DIR=/opt/app-root/src \
  --env NOTEBOOK_BASE_URL="${BASE_PATH}" \
  --env NOTEBOOK_ARGS=$'--ServerApp.port=8888\n--ServerApp.token=\'\'\n--ServerApp.password=\'\'\n--ServerApp.quit_button=False' \
  --env OFFLINE_FAKE_VALUE="${FAKE_VALUE}" \
  "${WORKBENCH_IMAGE}" >/dev/null
workbench_started=1

# Keep the isolation contract executable: the unique network is internal,
# neither container publishes a port, and neither has a runtime socket mount.
internal=$("${ENGINE}" network inspect --format '{{.Internal}}' "${NETWORK_NAME}")
[[ "${internal}" == "true" ]] || {
  echo "Expected internal network, got: ${internal}" >&2
  exit 1
}
workbench_networks=$("${ENGINE}" inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{printf "%s\n" $name}}{{end}}' "${WORKBENCH_NAME}")
[[ "${workbench_networks}" == "${NETWORK_NAME}" ]] || {
  echo "Workbench has unexpected network attachments: ${workbench_networks}" >&2
  exit 1
}
port_bindings=$("${ENGINE}" inspect --format '{{json .HostConfig.PortBindings}}' "${WORKBENCH_NAME}")
[[ -z "${port_bindings}" || "${port_bindings}" == "null" || "${port_bindings}" == "{}" ]] || {
  echo "Workbench unexpectedly has published ports: ${port_bindings}" >&2
  exit 1
}
mounts=$("${ENGINE}" inspect --format '{{json .Mounts}}' "${WORKBENCH_NAME}")
[[ "${mounts}" != *docker.sock* && "${mounts}" != *podman.sock* ]] || {
  echo "Workbench unexpectedly has a container-runtime socket mount" >&2
  exit 1
}

if ! "${ENGINE}" exec "${WORKBENCH_NAME}" python3 -c \
  "from pathlib import Path; v4=any(len(r.split())>1 and r.split()[1]=='00000000' for r in Path('/proc/net/route').read_text().splitlines()[1:]); v6=any((p:=r.split())[0]=='0'*32 and p[1]=='00' and p[-1]!='lo' for r in Path('/proc/net/ipv6_route').read_text().splitlines() if r.split()); raise SystemExit(1 if v4 or v6 else 0)"; then
  echo "Workbench unexpectedly has a default IPv4/IPv6 route" >&2
  exit 1
fi

started_at=$(date +%s)
while true; do
  if "${ENGINE}" exec "${WORKBENCH_NAME}" python3 -c \
  "import urllib.request; urllib.request.urlopen('${READINESS_URL}api', timeout=2).read()" \
    >/dev/null 2>&1; then
    break
  fi
  if (( $(date +%s) - started_at >= STARTUP_TIMEOUT )); then
    echo "Workbench did not become ready within ${STARTUP_TIMEOUT}s" >&2
    exit 1
  fi
  sleep 2
done

# Fixture setup is backend-only. The browser performs the modification,
# staging, and commit through JupyterLab's visible Git UI.
"${ENGINE}" exec "${WORKBENCH_NAME}" bash -lc '
  set -Eeuo pipefail
  git config --global user.name "Offline Browser Fixture"
  git config --global user.email "offline-browser@example.invalid"
  mkdir -p /opt/app-root/src/offline-git-remote.git /opt/app-root/src/offline-git-repo
  git -C /opt/app-root/src/offline-git-remote.git init --bare
  git -C /opt/app-root/src/offline-git-repo init
  printf "%s\\n" "initial content" > /opt/app-root/src/offline-git-repo/git-ui.txt
  git -C /opt/app-root/src/offline-git-repo add git-ui.txt
  git -C /opt/app-root/src/offline-git-repo commit -m "initial offline fixture"
  git -C /opt/app-root/src/offline-git-repo remote add origin file:///opt/app-root/src/offline-git-remote.git
' >/dev/null

runner_id=$("${ENGINE}" run --pull=never --detach \
  --name "${RUNNER_NAME}" \
  --network "${NETWORK_NAME}" \
  --network-alias browser \
  --env CI=true \
  --env OFFLINE_BASE_URL="${BASE_URL}" \
  --env TEST_TARGET="${WORKBENCH_IMAGE}" \
  --env OFFLINE_FAKE_VALUE="${FAKE_VALUE}" \
  --volume "${OFFLINE_SPEC_PATH}:/home/pwuser/tests/browser/tests/jupyter-offline.spec.ts:ro,Z" \
  --volume "${PLAYWRIGHT_CONFIG_PATH}:/home/pwuser/tests/browser/playwright.config.ts:ro,Z" \
  --volume "${OFFLINE_MODELS_PATH}:/home/pwuser/tests/browser/tests/models/jupyterlab:ro,Z" \
  --volume "${RESULTS_DIR}:/home/pwuser/tests/browser/results:rw,Z" \
  "${BROWSER_IMAGE}" \
  --config=playwright.config.ts \
  "${PLAYWRIGHT_ARGS[@]}")
runner_started=1

runner_networks=$("${ENGINE}" inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{printf "%s\n" $name}}{{end}}' "${RUNNER_NAME}")
[[ "${runner_networks}" == "${NETWORK_NAME}" ]] || {
  echo "Browser runner has unexpected network attachments: ${runner_networks}" >&2
  exit 1
}
runner_ports=$("${ENGINE}" inspect --format '{{json .HostConfig.PortBindings}}' "${RUNNER_NAME}")
[[ -z "${runner_ports}" || "${runner_ports}" == "null" || "${runner_ports}" == "{}" ]] || {
  echo "Browser runner unexpectedly has published ports: ${runner_ports}" >&2
  exit 1
}
runner_mounts=$("${ENGINE}" inspect --format '{{json .Mounts}}' "${RUNNER_NAME}")
[[ "${runner_mounts}" != *docker.sock* && "${runner_mounts}" != *podman.sock* ]] || {
  echo "Browser runner unexpectedly has a container-runtime socket mount" >&2
  exit 1
}
if ! "${ENGINE}" exec "${RUNNER_NAME}" node -e \
  "const fs=require('fs'); const v4=fs.readFileSync('/proc/net/route','utf8').split('\\n').slice(1).some(r=>r.trim().split(/\\s+/)[1]==='00000000'); const v6=fs.readFileSync('/proc/net/ipv6_route','utf8').split('\\n').some(r=>{const p=r.trim().split(/\\s+/); return p[0]==='0'.repeat(32)&&p[1]==='00'&&p.at(-1)!=='lo'}); process.exit(v4||v6?1:0)"; then
  echo "Browser runner unexpectedly has a default IPv4/IPv6 route" >&2
  exit 1
fi

started_at=$(date +%s)
while [[ "$("${ENGINE}" inspect --format '{{.State.Running}}' "${RUNNER_NAME}" 2>/dev/null || true)" == "true" ]]; do
  if (( $(date +%s) - started_at >= TEST_TIMEOUT )); then
    echo "Offline browser suite exceeded ${TEST_TIMEOUT}s" >&2
    "${ENGINE}" stop --time 5 "${RUNNER_NAME}" >/dev/null 2>&1
    status=124
    break
  fi
  sleep 2
done
status="${status:-$("${ENGINE}" inspect --format '{{.State.ExitCode}}' "${RUNNER_NAME}")}"
"${ENGINE}" logs "${RUNNER_NAME}" >"${RESULTS_DIR}/runner.log" 2>&1
exit "${status}"
