#!/usr/bin/env bash
# GPU smoke via Pod (no Notebook CR / RHOAI required). Run after nvidia.com/gpu allocatable.
set -euo pipefail

: "${NS:?Set NS to a unique, dedicated namespace — this is a shared account, never default to a personal name}"
: "${TAG:=rhoai-3.6-ea.1}"
: "${PULL_SECRET:=rhoai-pull}"
: "${TIMEOUT:=900}"
: "${CLUSTER_CONTEXT:?Set CLUSTER_CONTEXT to the exact kubeconfig context (e.g. \$(oc config current-context) captured right after login) — never rely on the ambient current-context, which another process on this machine can change mid-session}"

IMG="${1:?usage: $0 <full-image-ref>}"

# NS/PULL_SECRET/IMG are spliced directly into the YAML heredoc below with
# no serialization — reject anything that could break out of its scalar
# context (a newline, or a literal "---" document separator) before that
# happens. NS/PULL_SECRET are also constrained to valid Kubernetes names,
# which they need to be anyway.
for _var_name in NS PULL_SECRET; do
  _val="${!_var_name}"
  [[ "$_val" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || { echo "ERROR: $_var_name '$_val' is not a valid Kubernetes name" >&2; exit 1; }
done
[[ "$IMG" != *$'\n'* && "$IMG" != *"---"* ]] || { echo "ERROR: IMG contains a newline or '---' — refusing to interpolate into YAML" >&2; exit 1; }

hash_cmd() { command -v sha256sum >/dev/null 2>&1 && sha256sum || shasum -a 256; }
timeout_cmd() { command -v timeout >/dev/null 2>&1 && echo timeout || command -v gtimeout >/dev/null 2>&1 && echo gtimeout || { echo "ERROR: need GNU timeout (brew install coreutils for gtimeout on macOS)" >&2; exit 1; }; }
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
  oc --context "$CLUSTER_CONTEXT" delete pod "$POD" -n "$NS" --ignore-not-found --wait=true --timeout=30s >/dev/null 2>&1 || true
  sleep 3
}
trap cleanup EXIT

CMD='["sleep","infinity"]'
if [[ "$IS_RUNTIME" -eq 0 ]]; then
  CMD='null'
fi

cat <<EOF | oc --context "$CLUSTER_CONTEXT" apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  namespace: $NS
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  nodeSelector:
    kubernetes.io/arch: arm64
  tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
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
if ! oc --context "$CLUSTER_CONTEXT" wait --for=condition=Ready "pod/$POD" -n "$NS" --timeout="${TIMEOUT}s"; then
  echo "FAIL: pod not ready" >&2
  oc --context "$CLUSTER_CONTEXT" describe pod "$POD" -n "$NS" | tail -20
  exit 1
fi
SCHEDULED_NODE=$(oc --context "$CLUSTER_CONTEXT" get pod "$POD" -n "$NS" -o jsonpath='{.spec.nodeName}')
echo "==> Scheduled on node: $SCHEDULED_NODE"

case "$LIB" in
  torch)
    # if/raise, not assert — assert is a no-op under PYTHONOPTIMIZE, and a
    # SMOKE_PASS that can lie is worse than one that's merely verbose
    PY='import platform, torch
if platform.machine() != "aarch64": raise SystemExit(platform.machine())
if not torch.cuda.is_available(): raise SystemExit("cuda not available")
print("device:", torch.cuda.get_device_name(0))
print("sm:", torch.cuda.get_device_capability())
x = torch.randn(1024, 1024, device="cuda")
print("matmul_ok:", float((x @ x).mean().item()))
print("SMOKE_PASS")'
    ;;
  tensorflow)
    PY='import os, platform, tensorflow as tf
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
if platform.machine() != "aarch64": raise SystemExit(platform.machine())
gpus = tf.config.list_physical_devices("GPU")
print("gpus:", gpus)
if not gpus: raise SystemExit("no GPU devices")
tf.config.set_soft_device_placement(False)
with tf.device("/GPU:0"):
    x = tf.random.uniform([1024, 1024])
    result = tf.matmul(x, x)
if "GPU" not in result.device: raise SystemExit(result.device)
print("SMOKE_PASS")'
    ;;
  minimal)
    PY='import platform, subprocess
if platform.machine() != "aarch64": raise SystemExit(platform.machine())
out = subprocess.check_output(["nvidia-smi", "-L"], text=True)
print(out.strip())
if "GPU" not in out: raise SystemExit("no GPU in nvidia-smi -L output")
print("SMOKE_PASS")'
    ;;
esac

echo "==> Running GPU check ($LIB)..."
"$(timeout_cmd)" "${EXEC_TIMEOUT:-$TIMEOUT}s" oc --context "$CLUSTER_CONTEXT" exec -n "$NS" "$POD" -c smoke -- python -c "$PY"
echo "==> PASS $IMG"
