---
name: arm64-rosa-gpu-smoke
description: Validate ARM64 CUDA notebook/runtime images end-to-end — Konflux manifest audit (skopeo arm64), testcontainers CPU smoke (podman --platform linux/arm64), GPU smoke on ROSA G5g/T4G or rdu2 GH200 Grace Hopper (Pod + oc exec), ODH tests/manual GPU notebooks (nbconvert headless), and the Elyra pipeline UI test (tests/manual/runtime_elyra — Pipeline Runtime images, browser automation, not headless). Use for RHDS/RHOAI EA/GA multi-arch sign-off.
---

# ARM64 CUDA Image Validation

Full workflow: manifest audit → CPU testcontainers → G5g GPU smoke → manual GPU notebooks → results matrix.

Scripts: [`scripts/gpu-smoke-pod.sh`](scripts/gpu-smoke-pod.sh), [`scripts/gpu-manual-tests.py`](scripts/gpu-manual-tests.py).

## Phase 1: Konflux Manifest Audit

Verify multi-arch index includes `linux/arm64` for all in-scope images.

```bash
IMG=quay.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9:rhoai-3.6-ea.1
skopeo inspect --raw docker://$IMG | jq '.manifests[] | {arch: .platform.architecture, os: .platform.os, digest: .digest}'
# Scripted check: assert linux/arm64 is actually present, not just "arm64" under any os
skopeo inspect --raw docker://$IMG | jq -e '[.manifests[] | select(.platform.architecture=="arm64" and .platform.os=="linux")] | length > 0'
```

### In-scope images (RHOAI 3.6 EA1 example)

| Tier | Components | Expected archs |
|------|-----------|----------------|
| CPU workbenches | minimal-cpu, datascience-cpu, codeserver-datascience-cpu, trustyai-cpu | amd64, arm64, ppc64le, s390x |
| CPU runtimes | runtime-minimal-cpu, runtime-datascience-cpu | amd64, arm64, ppc64le, s390x |
| CUDA workbenches | minimal-cuda, pytorch-cuda, tensorflow-cuda, pytorch-llmcompressor-cuda | amd64, arm64 |
| CUDA runtimes | runtime-pytorch-cuda, runtime-tensorflow-cuda, runtime-pytorch-llmcompressor-cuda | amd64, arm64 |

**Out of scope (amd64-only):** ROCm workbenches/runtimes, RStudio.

### Image naming

Registry: `quay.io/rhoai/`

| Pattern | Example |
|---------|---------|
| Workbench | `odh-workbench-jupyter-<flavor>-<accel>-py312-rhel9` |
| Codeserver | `odh-workbench-codeserver-datascience-cpu-py312-rhel9` |
| Runtime | `odh-pipeline-runtime-<flavor>-<accel>-py312-rhel9` |
| LLMCompressor (full) | `odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312-rhel9` |

**Pitfall:** LLMCompressor uses full `odh-workbench-jupyter-pytorch-llmcompressor-*`, NOT abbreviated `odh-wb-*`.

### Negative check

ROCm images should be amd64-only (confirms exclusion is intentional):

```bash
IMG="quay.io/rhoai/odh-workbench-jupyter-pytorch-rocm-py312-rhel9:rhoai-3.6-ea.1"
RAW=$(skopeo inspect --raw "docker://$IMG")
# A genuinely amd64-only image has no manifest list at all (single-manifest
# response, no top-level .manifests) — jq '.manifests[]' would crash on it
# with "Cannot iterate over null" precisely in the expected-good case.
if echo "$RAW" | jq -e 'has("manifests")' >/dev/null; then
  echo "$RAW" | jq -e '[.manifests[] | {arch: .platform.architecture, os: .platform.os}] | unique == [{"arch":"amd64","os":"linux"}]' \
    || { echo "ERROR: $IMG is not amd64-only (unexpected — ROCm should be excluded from arm64)" >&2; exit 1; }
else
  skopeo inspect "docker://$IMG" | jq -e '.Architecture == "amd64" and .Os == "linux"' \
    || { echo "ERROR: $IMG is not amd64/linux (unexpected — ROCm should be excluded from arm64)" >&2; exit 1; }
fi
```

## Phase 2: CPU Testcontainers Smoke

Validates arm64 images boot, link libraries, and serve entrypoints without GPU.

### Environment setup

```bash
cd <notebooks-repo>
uv venv --python "$(which python3.14)" && uv sync --locked
export TESTCONTAINERS_RYUK_DISABLED=true
podman machine start  # macOS
```

### Per-image command

```bash
IMG=quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9:rhoai-3.6-ea.1
podman pull --platform linux/arm64 "$IMG"
uv run pytest tests/containers \
  -m 'not openshift and not cuda and not rocm and not manifest_validation' \
  --image="$IMG" -v
```

### CUDA images on CPU host

CUDA images fail `tests/containers/base_image_test.py::test_elf_files_can_link_runtime_libs` because:
- `libnvidia-ml.so.1` not present without GPU drivers (ucx libs)
- `libc10.so`, `libtorch_cpu.so` etc. not found by ldd (loaded at runtime via `LD_LIBRARY_PATH`)

These are **expected on CPU-only hosts**. Skip the ldd test:

```bash
uv run pytest tests/containers \
  -m 'not openshift and not cuda and not rocm and not manifest_validation' \
  --deselect=tests/containers/base_image_test.py::test_elf_files_can_link_runtime_libs \
  --image="$IMG" -v
```

Other workbench tests (Jupyter HTTP serve, entrypoint boot) still pass for CUDA images without GPU.

### Known test flakes / failures (rhoai-3.6-ea.1)

| Image | Test | Cause | Blocking? |
|-------|------|-------|-----------|
| codeserver-datascience-cpu | `test_mysql_connection` | `pip install mysql-connector-python` fails against RHOAI EA PyPI index (3/3 consistent) | ENV |
| tensorflow-cuda workbench | `test_ipv6_only` | IPv6-only network not available on test host | ENV — entrypoint passes with IPv6 disabled |
| pytorch-llmcompressor-cuda workbench | `test_image_entrypoint_starts`, `test_ipv6_only` | IPv6 env; entrypoint **PASS** with `disable_ipv6` sysctl | ENV — not arm64 boot defect |
| All CUDA runtimes | — | **PASS** on remote arm64 host — this run used `--ignore=base_image_test.py` (skips the whole file, not just the known ELF-link failure), so it's narrower coverage than the `--deselect` approach used elsewhere in this doc | — |

CUDA **runtime** images (`odh-pipeline-runtime-*-cuda-*`) passed CPU testcontainers on arm64; workbench CUDA images need follow-up on ipv6/entrypoint tests, not manifest/arch issues.

### Remote arm64 host (when Mac podman disk is full)

Run the same pytest loop on a Linux arm64 box (e.g. via SSH):

```bash
ssh user@host 'bash -s' <<'REMOTE'
set -euo pipefail
export TESTCONTAINERS_RYUK_DISABLED=true
cd ~/notebooks
IMG=quay.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9:rhoai-3.6-ea.1
podman pull --platform linux/arm64 "$IMG"
uv run pytest tests/containers \
  -m 'not openshift and not cuda and not rocm and not manifest_validation' \
  --deselect=tests/containers/base_image_test.py::test_elf_files_can_link_runtime_libs \
  --image="$IMG" -q
REMOTE
```

### Batch script pattern

Key points for a batch testcontainers script:
- Pull with `podman pull --platform linux/arm64` (requires `podman machine start` on macOS)
- Set `TESTCONTAINERS_RYUK_DISABLED=true`
- Deselect `base_image_test.py::test_elf_files_can_link_runtime_libs` for `*cuda*` images (not the whole file — other tests in it still apply)
- Never edit the script while it's running (mid-run edits cause shell parse errors)
- Output per-image log + TSV summary

## Phase 3: GPU testing on aarch64 + NVIDIA GPU

Two environments available:

| Environment | GPU | SM | VRAM | RHOAI? | Use for |
|-------------|-----|-----|------|--------|---------|
| **ROSA HCP g5g** | T4G | 7.5 | 16 GB | No (bare pods) | Minimum-SM validation, cost-efficient |
| **rdu2 OCP (GH200)** | NVIDIA GH200 480GB | **9.0** | **102 GB** | **Yes (3.5 EA1)** | Grace Hopper validation, BF16, large models |

### rdu2 Grace Hopper cluster

**Cluster:** `ocp2.sys.eng.rdu2.dc.redhat.com` — OCP 5.0 EC, all aarch64 nodes.

**GPU node:** `nvd-srv-18` — 4× NVIDIA GH200 480GB, CUDA driver 580, CUDA 13.0, cuDNN 91900.

**Access:**

```bash
oc login --web "https://<api-server>:6443"
# Capture the exact context name immediately — this is a SECOND, DIFFERENT
# cluster from the ROSA one used elsewhere in this doc. Never rely on
# ambient current-context for either; always pass --context explicitly
# (see rosa-hcp-provision/SKILL.md's "Critical: always pass --context"
# section for why — a real incident had oc silently hit the wrong cluster
# mid-session because something else on the same machine changed it).
export RDU2_CONTEXT=$(oc config current-context)
oc --context "$RDU2_CONTEXT" whoami --show-server   # sanity check
```

(The real rdu2 API server hostname is internal-only — get it from whoever
grants you cluster access. Don't use `--insecure-skip-tls-verify`; it
disables certificate validation for all subsequent API calls.)

**Important:** RHOAI 3.5 images on this cluster are **amd64-only** (`registry.redhat.io`). To test arm64 EA images, create a pull secret for `quay.io/rhoai` (copy from ROSA cluster or personal auth). `$CLUSTER_CONTEXT` here is the ROSA cluster's context captured in `## Cluster prerequisites` below — set that up first if you haven't:

```bash
set -euo pipefail
: "${RDU2_NAMESPACE:?Set RDU2_NAMESPACE to a unique, dedicated namespace on the rdu2 cluster — never default to a personal name}"
: "${TEST_NAMESPACE:?Set TEST_NAMESPACE to the namespace already set up on the ROSA cluster below}"
oc --context "$RDU2_CONTEXT" create ns "$RDU2_NAMESPACE"   # fails loudly if it already exists — don't silently reuse another operator's namespace
# Get auth from the ROSA cluster context (or personal docker config)
SECRET_FILE=$(umask 077 && mktemp)
trap 'rm -f "$SECRET_FILE"' EXIT
# GNU base64 uses -d, macOS/BSD base64 uses -D — python3 sidesteps the
# flag difference entirely rather than guessing; only fall back to a
# specific flag if python3 truly isn't available.
base64_decode() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys, base64; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))'
  elif base64 --version >/dev/null 2>&1; then
    base64 -d   # GNU coreutils supports --version
  else
    base64 -D   # BSD/macOS base64 has no --version
  fi
}
oc --context "$CLUSTER_CONTEXT" whoami --show-server   # confirm this is really the ROSA cluster before reading its secret
oc get secret rhoai-pull -n "$TEST_NAMESPACE" --context="$CLUSTER_CONTEXT" \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64_decode > "$SECRET_FILE"
oc --context "$RDU2_CONTEXT" create secret generic rhoai-pull -n "$RDU2_NAMESPACE" \
  --from-file=.dockerconfigjson="$SECRET_FILE" \
  --type=kubernetes.io/dockerconfigjson
```

Then deploy pods against `nvd-srv-18`, using `nodeSelector` (not
`nodeName`, so the scheduler still evaluates GPU/toleration matching
instead of blindly binding to the node) plus the `nvidia.com/gpu`
toleration used elsewhere in this doc:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gh200-smoke
  namespace: "<RDU2_NAMESPACE>"
spec:
  automountServiceAccountToken: false
  imagePullSecrets:
  - name: rhoai-pull
  nodeSelector:
    kubernetes.io/hostname: nvd-srv-18.nvidia.eng.rdu2.redhat.com
  tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
  containers:
  - name: smoke
    image: "<image-under-test>"
    resources:
      requests: {nvidia.com/gpu: "1"}
      limits: {nvidia.com/gpu: "1"}
    command: ["sleep", "infinity"]
```

**GH200 reference benchmarks (rhoai-3.6-ea.1, PyTorch):**

| Dtype | 4096² | 8192² | 16384² |
|-------|-------|-------|--------|
| FP32 | 50 TFLOPS, 2.7ms | 51 TFLOPS, 21.5ms | 54 TFLOPS, 163ms |
| FP16 | 612 TFLOPS, 0.2ms | 812 TFLOPS, 1.4ms | 727 TFLOPS, 12ms |
| BF16 | 503 TFLOPS, 0.3ms | 630 TFLOPS, 1.7ms | **839 TFLOPS**, 10.5ms |

BF16 is **GH200-only** (SM 9.0); T4G (SM 7.5) does not support BF16.

VRAM stress: FP16 40960² (6.7 GB alloc) completes in 202ms, no NaN/Inf.

### ROSA G5g hardware context

Only G5g is available for ARM+GPU on ROSA. See [rosa-hcp-provision skill](../rosa-hcp-provision/SKILL.md#aws-arm64-gpu-landscape-as-of-jul-2026) for full instance listing and sources.

| Instance | CPU | GPU | SM | On ROSA? | Notes |
|----------|-----|-----|-----|----------|-------|
| **g5g.2xlarge** | 8× Graviton2 (aarch64) | 1× T4G (16 GB) | **7.5** | **Yes — recommended** | DTK ~30 min; $0.56/hr |
| g5g.xlarge | 4× Graviton2 (aarch64) | 1× T4G (16 GB) | 7.5 | Yes — avoid | Memory stall during driver compile |
| g5g.16xlarge | 64× Graviton2 | 2× T4G (32 GB) | 7.5 | Yes | Multi-GPU testing; $2.74/hr |
| P6e-GB200 | Grace (aarch64) | GB200 NVL72 | 10.0 | **No** | [UltraServer only](https://aws.amazon.com/ec2/instance-types/p6/), Dallas Local Zone, Capacity Blocks |
| GH200 | Grace (aarch64) | Hopper H100 | 9.0 | **No** on ROSA; **yes** on rdu2 OCP | See rdu2 cluster above |

### V100 pitfall (from ntbcudashrd experience)

Do **not** use V100 (sm_70) for torch 2.7+ / cu128 validation — minimum SM is **7.5** (T4G).

### Cluster prerequisites

See [rosa-hcp-provision skill](../rosa-hcp-provision/SKILL.md):

1. ROSA HCP cluster + **`g5g.2xlarge`** pool — `gpu-arm` by default (the
   primary pool from `rosa-hcp-provision/SKILL.md`'s "GPU Machine Pools"
   section), or `gpu-arm2` if you resized per that skill's "Resize GPU
   pool" section instead of creating `g5g.2xlarge` directly. Whichever
   pool is actually GPU-ready is `$GPU_POOL_NAME` below.
2. NFD + NVIDIA GPU Operator; driver **2/2 Ready**, `nvidia.com/gpu: 1`
3. **Pull secret** for `quay.io/rhoai` in test namespace (ROSA global pull-secret lacks rhoai)

```bash
set -euo pipefail
# CLUSTER_CONTEXT: this is the ROSA cluster from rosa-hcp-provision/SKILL.md
# — capture it there right after login and reuse the same value here rather
# than relying on ambient current-context.
: "${CLUSTER_CONTEXT:?Set CLUSTER_CONTEXT to the ROSA cluster exact kubeconfig context}"
: "${TEST_NAMESPACE:?Set TEST_NAMESPACE to a unique, dedicated namespace — this is a shared account, never default to a personal name}"
oc --context "$CLUSTER_CONTEXT" create ns "$TEST_NAMESPACE"   # fails loudly if it already exists — don't silently reuse another operator's namespace (set -e above stops the script here on failure)

# This skill does NOT read your local ~/.docker/config.json automatically —
# a skill executed by an agent that silently harvests a local registry
# credential and pushes it into a cluster Secret is a real credential-theft
# pattern, independently flagged in review. create-pull-secret.sh reads the
# token interactively so it never lands in argv/ps/history:
oc config use-context "$CLUSTER_CONTEXT"
.cursor/skills/lib/create-pull-secret.sh rhoai-pull "$TEST_NAMESPACE" quay.io
# (or, if you already have a dockerconfigjson you trust from your own
# secret-manager workflow — not your default Docker CLI config —
# `oc create secret generic rhoai-pull -n "$TEST_NAMESPACE"
# --from-file=.dockerconfigjson=<path-you-trust> --type=kubernetes.io/dockerconfigjson`)

oc --context "$CLUSTER_CONTEXT" label namespace "$TEST_NAMESPACE" pod-security.kubernetes.io/enforce=baseline
```

Verify GPU ready:

```bash
oc --context "$CLUSTER_CONTEXT" wait --for=condition=Ready pod -l app.kubernetes.io/component=nvidia-driver -n nvidia-gpu-operator --timeout=1800s
GPU_NODE=$(oc --context "$CLUSTER_CONTEXT" get node -l nvidia.com/gpu.present=true,kubernetes.io/arch=arm64 -o json)
[ "$(echo "$GPU_NODE" | jq '.items | length')" -gt 0 ] || { echo "ERROR: no arm64 GPU node found (mixed-arch cluster? check nodeSelector)" >&2; exit 1; }
echo "$GPU_NODE" | jq -r '.items[0] | "\(.metadata.name) gpu=\(.status.allocatable["nvidia.com/gpu"]) type=\(.metadata.labels["node.kubernetes.io/instance-type"])"'
```

### Phase 3a — Quick GPU smoke (matmul / nvidia-smi)

One Pod per image, pinned to GPU node, sequential (single GPU).

```bash
cd <notebooks-repo>
export TAG=rhoai-3.6-ea.1
export NS="$TEST_NAMESPACE"   # reuse the namespace validated in "Cluster prerequisites" above — never hardcode a personal name
export CLUSTER_CONTEXT   # already set above — the script requires it explicitly
.cursor/skills/arm64-rosa-gpu-smoke/scripts/gpu-smoke-pod.sh \
  quay.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9:$TAG
```

| Image type | Check |
|------------|-------|
| `*pytorch*` | `torch.cuda` matmul on T4G, sm (7,5) |
| `*tensorflow*` | `tf.config.list_physical_devices('GPU')` |
| `*minimal-cuda*` | `nvidia-smi -L` |

Runtime images use `sleep infinity` entrypoint override in the script.

### Phase 3b — Manual GPU notebooks (`tests/manual` from ODH main)

Source: [opendatahub-io/notebooks/tests/manual](https://github.com/opendatahub-io/notebooks/tree/main/tests/manual)

| Notebook | Applies to |
|----------|--------------|
| `gpu-test-notebook.ipynb` | All CUDA workbench + runtime images with torch or TF |
| `pytorch-test-notebook.ipynb` | pytorch-cuda, llmcompressor-cuda (+ runtime variants) |
| `tensorflow-test.ipynb` | tensorflow-cuda (+ runtime variant) |
| `runtime_elyra/` | **Not headless** — Elyra UI / S3 pipeline workflow, see Phase 3c below |

**Procedure:** spawn GPU Pod → **non-interactive exec** → default `python` → `jupyter nbconvert --execute`. Do **not** open Jupyter Lab.

**`oc exec` flags (faster headless runs):**

- `-q` / `--quiet` — less client noise
- **Omit** `-i` and `-t` — no stdin/TTY (much faster, script-friendly)
- `-c smoke` — container name from scripts

Example:

```bash
export NOTEBOOK_REV=<full-40-char-commit-sha>   # pin the reviewed tests/manual revision — required, not "main"
: "${NOTEBOOK_REV:?Set NOTEBOOK_REV to a reviewed full commit SHA}"
[[ "$NOTEBOOK_REV" =~ ^[0-9a-f]{40}$ ]] || { echo "NOTEBOOK_REV must be a full 40-character lowercase commit SHA" >&2; exit 2; }
# set -e + a per-run mktemp path (not a fixed /tmp/gpu-test.ipynb): without
# these, a failed curl leaves nbconvert executing stale content from a prior
# run and reporting a result for the wrong revision. NOTEBOOK_REV is passed
# as a quoted positional parameter, not interpolated into the script text.
oc --context "$CLUSTER_CONTEXT" exec -q -n "$TEST_NAMESPACE" "$POD" -c smoke -- bash -lc '
  set -euo pipefail
  rev="$1"
  tmp_nb=$(mktemp --suffix=.ipynb)
  trap "rm -f \"$tmp_nb\"" EXIT
  curl -fsSL --connect-timeout 30 --max-time 300 -o "$tmp_nb" "https://raw.githubusercontent.com/opendatahub-io/notebooks/${rev}/tests/manual/gpu-test-notebook.ipynb"
  cd /opt/app-root/src
  python -m jupyter nbconvert --ExecutePreprocessor.timeout=1800 \
    --to notebook --execute "$tmp_nb" --output /tmp/out.ipynb
' -- "$NOTEBOOK_REV"
```

**Accepted residual risk:** `NOTEBOOK_REV` is validated to be a full
40-hex-character commit SHA (format only, not that it's an *approved*
revision — a malicious SHA on some fork/branch would still pass this
check). `tests/manual` is a fast-moving fixture directory with no
release/signing process, and this is a personal, single-operator
validation tool, not unattended automation — building and maintaining a
signed-revision allowlist is disproportionate here. The SHA pin (no
`main` fallback) plus the `set -e`/tempfile fix above are the
proportionate mitigations; know what's pinned before running it.

**Batch all 7 ARM CUDA images:**

```bash
cd <notebooks-repo>
export TAG=rhoai-3.6-ea.1
export TEST_NAMESPACE   # already set (see "Cluster prerequisites" above) — never hardcode a personal name
export CLUSTER_CONTEXT   # already set (see "Cluster prerequisites" above) — required, no ambient fallback
export NOTEBOOK_REV=<full-40-char-commit-sha>   # required — see Phase 3b example above
uv run .cursor/skills/arm64-rosa-gpu-smoke/scripts/gpu-manual-tests.py
# Single image:
uv run .cursor/skills/arm64-rosa-gpu-smoke/scripts/gpu-manual-tests.py --image "pytorch-cuda workbench" --exact
```

Uses Kubernetes stream exec (equivalent to `oc exec -q`) if local `oc` hangs. Log: `gpu-manual-tests.log`.

**Image → notebook matrix (validated rhoai-3.6-ea.1 on G5g/T4G):**

| Image | gpu-test | pytorch-test | tensorflow-test |
|-------|----------|--------------|-------------------|
| minimal-cuda workbench | subset† | — | — |
| pytorch-cuda workbench | ✓ | ✓ | — |
| tensorflow-cuda workbench | ✓ | — | ✓ |
| llmcompressor-cuda workbench | ✓ | ✓ | — |
| runtime-pytorch-cuda | ✓ | ✓ | — |
| runtime-tensorflow-cuda | ✓ | — | ✓ |
| runtime-llmcompressor-cuda | ✓ | ✓ | — |

† **minimal-cuda:** full `gpu-test-notebook` fails (no torch/TF). Run manual sections 5–6 only: `nvidia-smi -L`, `nvcc --version` (script handles automatically).

**Headless workarounds:**

| Issue | Fix |
|-------|-----|
| `tensorflow-test` `KeyError: NB_PREFIX` | Export `NB_PREFIX=/` before nbconvert; allow errors on TensorBoard cell |
| nbconvert output not in stdout | Validate executed `.ipynb` cell outputs (script does this) |
| Transient `nvidia.com/gpu unavailable` | Wait 5s between Pod deletes; retry |
| `oc` client hangs | Use `gpu-manual-tests.py` (Python kubernetes client) or `curl` to API |

### Pass/fail criteria (GPU phases)

| Check | T4G (ROSA) | GH200 (rdu2) |
|-------|------------|--------------|
| `platform.machine()` | `aarch64` | `aarch64` |
| GPU device visible | T4G (`nvidia-smi`, torch, TF) | NVIDIA GH200 480GB |
| SM capability | `(7, 5)` | `(9, 0)` |
| VRAM | 16 GB | 102 GB |
| BF16 matmul | N/A (unsupported) | Must pass, >500 TFLOPS |
| FashionMNIST training | Pass | Pass |
| TF MNIST training | Pass, >95% acc | Pass, >95% acc |
| Manual notebooks | All applicable cells execute | All applicable cells execute |

### Phase 3c — Elyra pipeline UI test (`tests/manual/runtime_elyra`)

Verified end-to-end on ROSA HCP arm64 (`jd-arm64-36e1`, RHOAI 3.6.0-ea.1) via
browser automation (`mcp__chrome-devtools__*` tools). This is a genuine UI
test — Elyra's Pipeline Editor has no headless/CLI equivalent, unlike
Phase 3b's `nbconvert` notebooks. It exercises **Pipeline Runtime images**
(`odh-pipeline-runtime-*`), a different image tier from the CUDA workbench/
runtime images Phases 1–3b cover — this test is CPU-only and validates the
Elyra/Kubeflow-Pipelines execution path, not GPU compute.

**Prerequisites:**

1. **`aipipelines` DSC component must be `Managed`** — RHOAI 3.6-ea.1 renamed
   `datasciencepipelines` to `aipipelines`; it's `Removed` by default on a
   minimal DSC (see `install-rhoai.md`'s minimal component list). Enable it:
   ```bash
   oc --context "$CLUSTER_CONTEXT" patch dsc default-dsc --type merge \
     -p '{"spec":{"components":{"aipipelines":{"managementState":"Managed"}}}}'
   oc --context "$CLUSTER_CONTEXT" wait --for=jsonpath='{.status.phase}'=Ready \
     dsc/default-dsc --timeout=120s
   ```
2. **An S3-compatible object storage backend** for the Data Science Pipelines
   Application (DSPA) to store artifacts. No AWS credentials needed —
   [rosa-hcp-provision/object_storage.md](../rosa-hcp-provision/object_storage.md)'s
   Garage recipe works well for this (already verified with `restricted-v2`,
   no `anyuid`). Create a dedicated bucket + key:
   ```bash
   oc --context "$CLUSTER_CONTEXT" exec garage-0 -n garage -c garage -- /garage bucket create elyra-pipelines
   oc --context "$CLUSTER_CONTEXT" exec garage-0 -n garage -c garage -- /garage key create elyra-key
   oc --context "$CLUSTER_CONTEXT" exec garage-0 -n garage -c garage -- /garage bucket allow \
     --read --write --owner elyra-pipelines --key elyra-key
   ```

**Gotcha — Elyra's S3 client ignores the configured region (RHOAIENG-82579).**
Elyra's `elyra/util/cos.py` `CosClient` builds its `minio.Minio()` client
with **no `region` argument at all**, and the `kfp`-schema runtime-config
metadata RHOAI auto-generates for the notebook (`~/.local/share/jupyter/
metadata/runtimes/odh_dsp.json`) has no region field either. The `minio`
client's own default resolves to `us-east-1` regardless of what region the
DSPA/pipeline-server was actually configured with. Against a backend that
enforces strict AWS SigV4 region-scope matching (Garage does), clicking
*Run Pipeline* in the Pipeline Editor fails at the pre-flight connectivity
check:
```
Error connecting to cloud storage: S3 operation failed; code: AuthorizationHeaderMalformed,
message: Authorization header malformed, unexpected scope: '<date>/us-east-1/s3/aws4_request',
expected: '<date>/<actual-region>/s3/aws4_request', ...
```
This happens even though the DSPA's own server-side pods (which use a
different, region-aware S3 client) work fine — only the notebook-side
Elyra pre-flight check breaks. **Fix**: set the object store's own region
to literally `us-east-1` so it matches Elyra's implicit default, and keep
the DSPA CR's `objectStorage.externalStorage.region` in sync with it
(dashboard's "Configure pipeline server" won't let you edit region after
creation — patch the DSPA CR directly instead):
```bash
# Garage: edit garage.s3.api.region in the Helm values, then restart to pick up the new ConfigMap
helm --kube-context "$CLUSTER_CONTEXT" upgrade garage <chart-path> -n garage \
  --reuse-values --set garage.s3.api.region=us-east-1
oc --context "$CLUSTER_CONTEXT" rollout restart statefulset/garage -n garage
# Keep the DSPA's region in sync (dashboard UI can't edit an existing pipeline server's config)
oc --context "$CLUSTER_CONTEXT" patch dspa dspa -n "$TEST_NAMESPACE" --type merge \
  -p '{"spec":{"objectStorage":{"externalStorage":{"region":"us-east-1"}}}}'
```
No upstream/RHOAIENG issue existed for this before — filed as
[RHOAIENG-82579](https://redhat.atlassian.net/browse/RHOAIENG-82579).

**Procedure** (dashboard + JupyterLab, via `mcp__chrome-devtools__*`):

1. **Create an S3 connection** in the Data Science Project → Connections tab:
   type "S3 compatible object storage - v1", endpoint
   `http://garage.<namespace>.svc.cluster.local:3900`, region `us-east-1`
   (per the gotcha above), the bucket/key from the prerequisites step.
2. **Configure the pipeline server** (Pipelines tab → Configure pipeline
   server), filling the same access key/secret/endpoint/region/bucket —
   the "Autofill from connection" dropdown menu items don't render in an
   accessibility-tree snapshot (see UI automation notes below), so fill
   the fields directly instead of relying on that shortcut.
3. **Create a workbench** with a Data-Science image (`Jupyter | Data
   Science | CPU | Python 3.12` — has Elyra preinstalled; confirmed by the
   Pipeline Editor / Runtimes / Runtime Images tabs appearing in the
   JupyterLab left sidebar and the Launcher's "Elyra" section).
4. **Clone the sample repo** via JupyterLab's Git Clone button:
   `https://github.com/harshad16/data-science-pipeline-example`, open
   `iris/iris-elyra.pipeline`.
5. **Assign a Pipeline Runtime image to every node** (`create-dataset`,
   `normalize-dataset`, `train-model`): click each node, open the Node
   Properties panel ("Open Panel" toolbar button), set **Runtime Image**
   from the dropdown — RHOAI populates this list from the cluster's
   `runtime-*` ImageStreams (e.g. `Runtime | Datascience | CPU | Python
   3.12 | Latest` → resolves to
   `quay.io/rhoai/odh-pipeline-runtime-datascience-cpu-py312-rhel9`).
6. **Save, then Run Pipeline** (toolbar). A "Job submission to Pipelines
   succeeded" dialog confirms the Argo Workflow was created; verify actual
   completion and arch on the cluster (dashboard/JupyterLab won't tell you
   which node it landed on):
   ```bash
   oc --context "$CLUSTER_CONTEXT" get workflows -n "$TEST_NAMESPACE"
   # once Succeeded, confirm arm64 + the expected runtime image per step pod:
   oc --context "$CLUSTER_CONTEXT" get pod <container-impl-pod> -n "$TEST_NAMESPACE" \
     -o jsonpath='{.spec.nodeName}{"\n"}{.spec.containers[*].image}{"\n"}'
   oc --context "$CLUSTER_CONTEXT" get node <node-name> -L kubernetes.io/arch
   ```

**Verified this session:** `Runtime | Datascience | CPU | Python 3.12 |
Latest` (`odh-pipeline-runtime-datascience-cpu-py312-rhel9`, confirmed
multi-arch amd64/arm64/ppc64le/s390x via `skopeo` beforehand) ran all 3
pipeline steps to completion (`Return code: 0` each) on an arm64 node,
including S3 artifact upload/download through Garage and the
`odh-data-science-pipelines-argo-argoexec-rhel9` sidecar (also confirmed
multi-arch). **Not exercised this session**: the other Runtime Image
options in the same dropdown (`Minimal`, `PyTorch CUDA`, `PyTorch LLM
Compressor CUDA`, `TensorFlow CUDA`, plus their ROCm counterparts) —
repeat steps 5–6 per image to extend coverage.

**UI automation notes (`mcp__chrome-devtools__*`):**

- **PatternFly `TypeaheadSelect`-style comboboxes don't expose their
  options in an accessibility-tree snapshot while open** — confirmed via
  direct DOM/ARIA inspection to be a real bug
  ([RHOAIENG-76231](https://redhat.atlassian.net/browse/RHOAIENG-76231),
  already tracked, in `Review`): the popper menu container has
  `aria-hidden="true"` while visibly open, and the combobox lacks
  `aria-controls`/`aria-activedescendant`. Hit this on "Create connection"
  → Connection type, and "Configure pipeline server" → Autofill from
  connection. **Workaround**: click the combobox, then `press_key`
  `ArrowDown` + `Enter` instead of trying to click a listed option by uid.
  Plain PatternFly `Select` "Options menu" dropdowns (e.g. workbench image
  picker, pipeline Node Properties' Runtime Image field) don't have this
  bug — their options *do* show up in a normal `take_snapshot` and can be
  clicked directly by uid.
- **The Pipeline Editor's Node Properties side panel shrinks the canvas**
  and can push nodes further right off-screen. If a node's uid becomes
  stale or a click doesn't land, close the panel ("Close Panel" toolbar
  button) to get the full-width canvas back, click the node's label text
  element (a plain `<span>`/`<div>`, not an accessible role) to select it,
  then reopen the panel — the Node Properties form updates for the newly
  selected node.
- Elyra's "Run pipeline" confirmation dialog's Runtime Configuration
  dropdown auto-selects the single RHOAI-provisioned option ("Pipeline")
  with no action needed — this is a plain `<select>`-style combobox, not
  the buggy typeahead variant.

### Teardown (when done billing)

```bash
oc --context "$CLUSTER_CONTEXT" whoami --show-server   # confirm you're pointed at the right cluster before a --yes deletion
# GPU_POOL_NAME must match whichever pool you actually created/GPU-tested
# above — restrict to the two names this doc's workflow can actually
# produce, so a typo can't --yes-delete an unrelated pool.
: "${GPU_POOL_NAME:?Set GPU_POOL_NAME to the pool you actually created (gpu-arm by default, gpu-arm2 if resized)}"
case "$GPU_POOL_NAME" in
  gpu-arm|gpu-arm2) ;;
  *) echo "ERROR: GPU_POOL_NAME must be gpu-arm or gpu-arm2, not '$GPU_POOL_NAME'" >&2; exit 1 ;;
esac
rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete machinepool \
  --cluster "$CLUSTER_NAME" "$GPU_POOL_NAME" --yes
# Optional: delete cluster — see rosa-hcp-provision skill
```

## Phase 4: Results Matrix

| Component | Manifest | testcontainers | GPU smoke (3a) | Manual notebooks (3b) | Elyra pipeline UI (3c) | Notes |
|-----------|----------|----------------|----------------|----------------------|------------------------|-------|
| …13 rows… | pass/fail | pass/fail | pass/fail/N/A | pass/fail/N/A | pass/fail/N/A | |

Rules:
- ROCm: manifest amd64-only expected; GPU columns N/A
- CPU images: GPU columns N/A
- CUDA ldd failures on CPU host: env issue, not blocking
- minimal-cuda manual: gpu-test **subset** counts as pass for 3b
- 3c only applies to Pipeline Runtime images (see Phase 3c) — N/A for
  workbench-only rows, but don't leave it blank for runtime rows; a blank
  cell reads as "not tracked," not "not applicable"

Template artifact: `.cursor-tmp-artifact/arm64-ea1-validation/results-matrix.md`

## Automation Gaps (follow-up, not blocking manual validation)

- `ci/cached-builds/gen_gha_matrix_jobs.py` `ARM64_COMPATIBLE` — **fixed** (6 → 15 targets), see RHAI-268; open question on whether to run all arm64 GHA jobs given Konflux already builds them
- `ci/find_images_for_test_matrix.py` tags are amd64-suffixed only
- `accelerator_image_test.py` skips minimal-cuda workbench

## Konflux Reference

- Branch: `rhoai-3.6-ea.1` → app `rhoai-v3-6-ea-1` on stone-prod-p02 (`rhoai-tenant`)
- Image tag: `quay.io/rhoai/<stem>-rhel9:rhoai-3.6-ea.1`
- Tekton push configs: `.tekton/*-v3-6-ea-1-push.yaml`
- CUDA images use `build-platforms: [linux/x86_64, linux-d160-m4xlarge/arm64]`
