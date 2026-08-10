#!/usr/bin/env bash
# GPU smoke via Pod (no Notebook CR / RHOAI required). Run after nvidia.com/gpu allocatable.
set -euo pipefail

: "${NS:=jdanek}"
: "${TAG:=rhoai-3.6-ea.1}"
: "${PULL_SECRET:=rhoai-pull}"
: "${TIMEOUT:=900}"

IMG="${1:?usage: $0 <full-image-ref>}"
hash_cmd() { command -v sha256sum >/dev/null 2>&1 && sha256sum || shasum -a 256; }
POD="gpu-smoke-$(printf '%s' "$IMG" | hash_cmd | cut -c1-16)-${RANDOM}${RANDOM}"

if [[ "$IMG" == *"-runtime-"* ]]; then
  IS_RUNTIME=1
else
  IS_RUNTIME=0
fi

if [[ "$IMG" == *"pytorch"* ]]; then
  LIB=torch
elif [[ "$IMG" == *"tensorflow"* ]]; then
  LIB=tensorflow
elif [[ "$IMG" == *"minimal-cuda"* ]]; then
  LIB=minimal
else
  echo "Unknown image type for $IMG" >&2
  exit 1
fi

cleanup() {
  oc delete pod "$POD" -n "$NS" --ignore-not-found --wait=true --timeout=30s >/dev/null 2>&1 || true
  sleep 3
}
trap cleanup EXIT

CMD='["sleep","infinity"]'
if [[ "$IS_RUNTIME" -eq 0 ]]; then
  CMD='null'
fi

cat <<EOF | oc apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  namespace: $NS
spec:
  restartPolicy: Never
  imagePullSecrets:
  - name: $PULL_SECRET
  containers:
  - name: smoke
    image: $IMG
$(if [[ "$IS_RUNTIME" -eq 1 ]]; then
cat <<INNER
    command: ["sleep", "infinity"]
INNER
fi)
    resources:
      limits:
        nvidia.com/gpu: "1"
      requests:
        nvidia.com/gpu: "1"
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
      runAsNonRoot: true
      seccompProfile:
        type: RuntimeDefault
    volumeMounts:
    - name: workspace
      mountPath: /opt/app-root/src
  volumes:
  - name: workspace
    emptyDir: {}
EOF

echo "==> Waiting for pod $POD (image pull may take several minutes)..."
if ! oc wait --for=condition=Ready "pod/$POD" -n "$NS" --timeout="${TIMEOUT}s"; then
  echo "FAIL: pod not ready" >&2
  oc describe pod "$POD" -n "$NS" | tail -20
  exit 1
fi
SCHEDULED_NODE=$(oc get pod "$POD" -n "$NS" -o jsonpath='{.spec.nodeName}')
echo "==> Scheduled on node: $SCHEDULED_NODE"

case "$LIB" in
  torch)
    PY='import platform, torch
assert platform.machine() == "aarch64", platform.machine()
assert torch.cuda.is_available(), "cuda not available"
print("device:", torch.cuda.get_device_name(0))
print("sm:", torch.cuda.get_device_capability())
x = torch.randn(1024, 1024, device="cuda")
print("matmul_ok:", float((x @ x).mean().item()))
print("SMOKE_PASS")'
    ;;
  tensorflow)
    PY='import os, platform, tensorflow as tf
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
assert platform.machine() == "aarch64", platform.machine()
gpus = tf.config.list_physical_devices("GPU")
print("gpus:", gpus)
assert gpus, "no GPU devices"
tf.config.set_soft_device_placement(False)
with tf.device("/GPU:0"):
    x = tf.random.uniform([1024, 1024])
    result = tf.matmul(x, x)
assert "GPU" in result.device, result.device
print("SMOKE_PASS")'
    ;;
  minimal)
    PY='import platform, subprocess
assert platform.machine() == "aarch64", platform.machine()
out = subprocess.check_output(["nvidia-smi", "-L"], text=True)
print(out.strip())
assert "GPU" in out
print("SMOKE_PASS")'
    ;;
esac

echo "==> Running GPU check ($LIB)..."
timeout "${EXEC_TIMEOUT:-$TIMEOUT}s" oc exec -n "$NS" "$POD" -c smoke -- python -c "$PY"
echo "==> PASS $IMG"
