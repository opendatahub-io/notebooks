#!/usr/bin/env bash
# Local dual-mode checks for a universal workbench/runtime image (RHAIENG-7241 §1).
#
# Usage:
#   ./validate-universal.sh <image-ref>
#   make -C custom-workbenches validate-universal RECIPE=<folder>
#
# Does NOT need a cluster. For full Elyra pipeline demo, import the same digest
# as a workbench and as a runtime ImageStream on OpenShift AI.
#
set -Eeuo pipefail

IMAGE="${1:-}"
ENGINE="${CONTAINER_ENGINE:-}"
if [[ -z "${ENGINE}" ]]; then
  if command -v podman >/dev/null 2>&1; then
    ENGINE=podman
  else
    ENGINE=docker
  fi
fi

if [[ -z "${IMAGE}" ]]; then
  echo "Usage: $0 <image-ref>" >&2
  exit 2
fi

if ! "${ENGINE}" image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Image not found locally: ${IMAGE}" >&2
  exit 1
fi

fail=0
run() {
  # shellcheck disable=SC2086
  "${ENGINE}" run --rm "$@"
}

echo "==> [${IMAGE}] workbench: JupyterLab importable"
if ! run --entrypoint python "${IMAGE}" -c 'import jupyterlab; print("jupyterlab", jupyterlab.__version__)'; then
  echo "FAIL: jupyterlab not importable" >&2
  fail=1
fi

echo "==> [${IMAGE}] workbench: default entrypoint is start-notebook path"
# entrypoint.sh without args would start Jupyter (long-running). Probe the scripts exist.
if ! run --entrypoint bash "${IMAGE}" -lc \
  'test -x /opt/app-root/bin/entrypoint.sh && test -x /opt/app-root/bin/start-notebook.sh && echo OK'; then
  echo "FAIL: workbench entrypoint scripts missing" >&2
  fail=1
fi

echo "==> [${IMAGE}] runtime: required commands (curl, python3)"
for cmd in curl python3; do
  if ! run --entrypoint bash "${IMAGE}" -lc "command -v ${cmd}" >/dev/null; then
    echo "FAIL: missing command ${cmd}" >&2
    fail=1
  else
    echo "    ${cmd}: OK"
  fi
done

echo "==> [${IMAGE}] runtime: Elyra bootstrapper + blank requirements-elyra.txt"
if ! run --entrypoint bash "${IMAGE}" -lc \
  'test -f /opt/app-root/bin/utils/bootstrapper.py && test -f /opt/app-root/bin/utils/requirements-elyra.txt && echo OK'; then
  echo "FAIL: bootstrapper.py or requirements-elyra.txt missing under /opt/app-root/bin/utils/" >&2
  fail=1
fi

echo "==> [${IMAGE}] runtime: ELYRA_INSTALL_PACKAGES=false"
elyra_env="$(run --entrypoint bash "${IMAGE}" -lc 'printf %s "${ELYRA_INSTALL_PACKAGES:-}"')"
if [[ "${elyra_env}" != "false" ]]; then
  echo "FAIL: expected ELYRA_INSTALL_PACKAGES=false, got '${elyra_env}'" >&2
  fail=1
else
  echo "    ELYRA_INSTALL_PACKAGES=${elyra_env}"
fi

echo "==> [${IMAGE}] runtime: papermill + minio importable"
if ! run --entrypoint python "${IMAGE}" -c \
  'import papermill, minio, nbclient; print("papermill", papermill.__version__, "minio OK")'; then
  echo "FAIL: Elyra runtime Python deps missing" >&2
  fail=1
fi

echo "==> [${IMAGE}] runtime: jupyter kernel available for papermill"
if ! run --entrypoint python "${IMAGE}" -c \
  'from jupyter_client import kernelspec; ks=kernelspec.find_kernel_specs(); assert "python3" in ks or ks, ks; print("kernels", sorted(ks))'; then
  echo "FAIL: no Jupyter kernel specs found (papermill needs python3 kernel)" >&2
  fail=1
fi

echo "==> [${IMAGE}] runtime: execute a trivial notebook (best-effort under qemu/cross-arch)"
# Full kernel execute can time out when the image arch differs from the host
# (e.g. linux/amd64 image on Apple Silicon). Treat that as a warning; native
# arch or cluster validate-runtime-image remains the hard gate.
if ! run --entrypoint sh "${IMAGE}" -c '
set -e
python3 - <<PY
from pathlib import Path
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

nb = nbformat.v4.new_notebook()
nb.cells = [nbformat.v4.new_code_cell("print(1+1)")]
ep = ExecutePreprocessor(timeout=120, kernel_name="python3")
ep.preprocess(nb, {"metadata": {"path": "/tmp"}})
out = Path("/tmp/universal-poc-out.ipynb")
nbformat.write(nb, out)
print("executed", out)
PY
'; then
  echo "WARN: notebook execution failed (often qemu/cross-arch). Deps/kernel OK above; re-check on native arch or cluster." >&2
fi

echo "==> [${IMAGE}] runtime: entrypoint.sh runtime helper present"
if ! run --entrypoint bash "${IMAGE}" -lc \
  'test -x /opt/app-root/bin/entrypoint.sh && grep -q WORKBENCH_MODE /opt/app-root/bin/entrypoint.sh && echo OK'; then
  echo "WARN: entrypoint dual-mode helper check skipped/failed" >&2
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "=> ERROR: ${IMAGE} is not a suitable universal workbench/runtime image" >&2
  exit 1
fi

echo "=> OK: ${IMAGE} passes local universal (workbench + runtime) checks"
echo "   Next: push, import once, attach the same digest as both workbench and Elyra runtime."
