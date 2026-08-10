---
name: arm64-rosa-gpu-smoke
description: Validate ARM64 CUDA notebook/runtime images end-to-end — Konflux manifest audit (skopeo arm64), testcontainers CPU smoke (podman --platform linux/arm64), GPU smoke on ROSA G5g/T4G or rdu2 GH200 Grace Hopper (Pod + oc exec), and ODH tests/manual GPU notebooks (nbconvert headless). Use for RHDS/RHOAI EA/GA multi-arch sign-off.
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
IMG=quay.io/rhoai/odh-workbench-jupyter-pytorch-rocm-py312-rhel9:rhoai-3.6-ea.1
skopeo inspect --raw docker://$IMG | jq '[.manifests[] | {arch: .platform.architecture, os: .platform.os}] | unique'
# Expect: [{"arch":"amd64","os":"linux"}]
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
| All CUDA runtimes | — | **PASS** on remote arm64 host with `--ignore=base_image_test.py` | — |

CUDA **runtime** images (`odh-pipeline-runtime-*-cuda-*`) passed CPU testcontainers on arm64; workbench CUDA images need follow-up on ipv6/entrypoint tests, not manifest/arch issues.

### Remote arm64 host (when Mac podman disk is full)

Run the same pytest loop on a Linux arm64 box (e.g. via SSH):

```bash
ssh user@host 'bash -s' <<'REMOTE'
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
```

(The real rdu2 API server hostname is internal-only — get it from whoever
grants you cluster access. Don't use `--insecure-skip-tls-verify`; it
disables certificate validation for all subsequent API calls.)

**Important:** RHOAI 3.5 images on this cluster are **amd64-only** (`registry.redhat.io`). To test arm64 EA images, create a pull secret for `quay.io/rhoai` (copy from ROSA cluster or personal auth):

```bash
oc create ns jdanek --dry-run=client -o yaml | oc apply -f -
# Get auth from ROSA cluster context (or personal docker config)
SECRET_FILE=$(umask 077 && mktemp)
trap 'rm -f "$SECRET_FILE"' EXIT
oc get secret rhoai-pull -n jdanek --context="<ROSA-context>" \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d > "$SECRET_FILE"
oc create secret generic rhoai-pull -n jdanek \
  --from-file=.dockerconfigjson="$SECRET_FILE" \
  --type=kubernetes.io/dockerconfigjson --dry-run=client -o yaml | oc apply -f -
```

Then deploy pods with `imagePullSecrets: [{name: rhoai-pull}]` and `nodeName: nvd-srv-18.nvidia.eng.rdu2.redhat.com`.

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

1. ROSA HCP cluster + **`g5g.2xlarge`** pool (`gpu-arm2`)
2. NFD + NVIDIA GPU Operator; driver **2/2 Ready**, `nvidia.com/gpu: 1`
3. **Pull secret** for `quay.io/rhoai` in test namespace (ROSA global pull-secret lacks rhoai)

```bash
: "${TEST_NAMESPACE:?Set TEST_NAMESPACE to a unique, dedicated namespace — this is a shared account, don't default to a personal name}"
oc create ns "$TEST_NAMESPACE"   # fails loudly if it already exists — don't silently reuse another operator's namespace

# This skill does NOT read your local ~/.docker/config.json automatically —
# a skill executed by an agent that silently harvests a local registry
# credential and pushes it into a cluster Secret is a real credential-theft
# pattern, independently flagged in review. Create the pull-secret yourself:
oc create secret docker-registry rhoai-pull -n "$TEST_NAMESPACE" \
  --docker-server=quay.io \
  --docker-username=<your-quay-username> \
  --docker-password=<your-quay-token-or-password> \
  --docker-email=unused@example.com
# (or, if you already have a dockerconfigjson you trust from your own
# secret-manager workflow — not your default Docker CLI config —
# `oc create secret generic rhoai-pull -n "$TEST_NAMESPACE"
# --from-file=.dockerconfigjson=<path-you-trust> --type=kubernetes.io/dockerconfigjson`)

oc label namespace "$TEST_NAMESPACE" pod-security.kubernetes.io/enforce=baseline
```

Verify GPU ready:

```bash
oc wait --for=condition=Ready pod -l app.kubernetes.io/component=nvidia-driver -n nvidia-gpu-operator --timeout=1800s
oc get node -l nvidia.com/gpu.present=true \
  -o jsonpath='{.items[0].metadata.name}{" gpu="}{.items[0].status.allocatable.nvidia\.com/gpu}{" type="}{.items[0].metadata.labels.node\.kubernetes\.io/instance-type}{"\n"}'
```

### Phase 3a — Quick GPU smoke (matmul / nvidia-smi)

One Pod per image, pinned to GPU node, sequential (single GPU).

```bash
cd <notebooks-repo>
export TAG=rhoai-3.6-ea.1
export NS=jdanek
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
| `runtime_elyra/` | **Not headless** — Elyra UI / S3 pipeline workflow |

**Procedure:** spawn GPU Pod → **non-interactive exec** → default `python` → `jupyter nbconvert --execute`. Do **not** open Jupyter Lab.

**`oc exec` flags (faster headless runs):**

- `-q` / `--quiet` — less client noise
- **Omit** `-i` and `-t` — no stdin/TTY (much faster, script-friendly)
- `-c smoke` — container name from scripts

Example:

```bash
export NOTEBOOK_REV=<full-40-char-commit-sha>   # pin the reviewed tests/manual revision — required, not "main"
# set -e + a per-run mktemp path (not a fixed /tmp/gpu-test.ipynb): without
# these, a failed curl leaves nbconvert executing stale content from a prior
# run and reporting a result for the wrong revision. NOTEBOOK_REV is passed
# as a quoted positional parameter, not interpolated into the script text.
oc exec -q -n jdanek "$POD" -c smoke -- bash -lc '
  set -euo pipefail
  rev="$1"
  tmp_nb=$(mktemp --suffix=.ipynb)
  trap "rm -f \"$tmp_nb\"" EXIT
  curl -fsSL -o "$tmp_nb" "https://raw.githubusercontent.com/opendatahub-io/notebooks/${rev}/tests/manual/gpu-test-notebook.ipynb"
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
export TEST_NAMESPACE=jdanek
export KUBECONFIG_CONTEXT='default/api-<cluster>-n953-p3-openshiftapps-com:443/admin'
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

### Teardown (when done billing)

```bash
rh-aws-saml-login iaps-rhods-odh-dev -- rosa delete machinepool \
  --cluster "$CLUSTER_NAME" gpu-arm2 --yes
# Optional: delete cluster — see rosa-hcp-provision skill
```

## Phase 4: Results Matrix

| Component | Manifest | testcontainers | GPU smoke (3a) | Manual notebooks (3b) | Notes |
|-----------|----------|----------------|----------------|----------------------|-------|
| …13 rows… | pass/fail | pass/fail | pass/fail/N/A | pass/fail/N/A | |

Rules:
- ROCm: manifest amd64-only expected; GPU columns N/A
- CPU images: GPU columns N/A
- CUDA ldd failures on CPU host: env issue, not blocking
- minimal-cuda manual: gpu-test **subset** counts as pass for 3b

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
