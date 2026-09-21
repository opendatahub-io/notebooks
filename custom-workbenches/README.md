# Custom workbenches (customer self-service)

Spike deliverable for [RHAIENG-7526](https://redhat.atlassian.net/browse/RHAIENG-7526) /
[RHAIENG-7241](https://redhat.atlassian.net/browse/RHAIENG-7241) (§2 custom images, §3 package collections).

## Layout

```text
custom-workbenches/
├── Makefile
├── interactive-image-builder.sh
├── src/                         # template + collections + wizard helpers
├── my-pytorch-cuda/             # generated (gitignored)
├── my-pytorch-rocm/
├── my-trustyai/
└── my-llmcompressor-cuda/
```

Replace `quay.io/MY-ORG/...` with your registry. Set `PUSH_IMAGES=no` to build
without pushing. All commands below run from this directory unless noted:

```bash
cd custom-workbenches
```

---

## Recommended workflow

AIPCC/RHEL bases need Red Hat entitlements for `dnf` during the image build.
**Do this once before the wizard** (full detail:
[docs/subscribed-builds.md](../docs/subscribed-builds.md)).

### 1. Set up entitlements

From a directory **without spaces** in the path (e.g. the notebooks repo root):

```bash
mkdir -p entitlement consumer

# macOS Apple Silicon: keep --platform=linux/amd64 so certs match amd64 builds.
# Linux x86_64: you can omit --platform.
podman run \
  --platform=linux/amd64 \
  -v "${PWD}/entitlement:/etc/pki/entitlement:Z" \
  -v "${PWD}/consumer:/etc/pki/consumer:Z" \
  --rm -t registry.access.redhat.com/ubi9/ubi \
  /usr/sbin/subscription-manager register \
    --org=18631088 --activationkey=YOUR_ACTIVATION_KEY
```

Ask your team for the activation key, or create one at
[console.redhat.com → Activation Keys](https://console.redhat.com/insights/connector/activation-keys).

Mount the certs into every podman build:

```bash
# macOS
podman machine ssh "printf '$(pwd)/entitlement:/etc/pki/entitlement\n$(pwd)/consumer:/etc/pki/consumer\n' | sudo tee /etc/containers/mounts.conf"

# Linux
printf "%s/entitlement:/etc/pki/entitlement\n%s/consumer:/etc/pki/consumer\n" "${PWD}" "${PWD}" \
  | sudo tee /etc/containers/mounts.conf
```

Verify (optional): `subscription-manager identity` and `dnf repolist` inside an
AIPCC base — see [docs/subscribed-builds.md](../docs/subscribed-builds.md).

ODH (CentOS Stream) wizard bases skip this step.

### 2. Generate a recipe

```bash
cd custom-workbenches
./interactive-image-builder.sh
# → creates e.g. my-pytorch-cuda/
```

### 3. Build (and optionally validate / push)

```bash
make build RECIPE=my-pytorch-cuda PUSH_IMAGES=no
make validate RECIPE=my-pytorch-cuda
make push RECIPE=my-pytorch-cuda
```

Then follow the smoke tests in the examples below.

---

## Example 1 — PyTorch + CUDA

**Prereq:** [entitlements](#1-set-up-entitlements) if you pick the AIPCC base.

**Wizard choices:** CUDA 13.0 → PyTorch → AIPCC (or ODH) base → AIPCC index →
`linux/amd64` → Quay org/repo → folder `my-pytorch-cuda`.

```bash
./interactive-image-builder.sh
# → creates my-pytorch-cuda/

make build RECIPE=my-pytorch-cuda PUSH_IMAGES=no
make validate RECIPE=my-pytorch-cuda
make push RECIPE=my-pytorch-cuda
```

Smoke test (CPU import; no GPU required):

```bash
podman run --rm --entrypoint python \
  quay.io/MY-ORG/my-pytorch-cuda:latest \
  -c 'import torch, torchvision; print("torch", torch.__version__, "cuda?", torch.cuda.is_available())'
```

With an NVIDIA GPU on the host:

```bash
podman run --rm --device nvidia --entrypoint python \
  quay.io/MY-ORG/my-pytorch-cuda:latest \
  -c 'import torch; print(torch.cuda.get_device_name(0)); x=torch.randn(2,3,device="cuda"); print(x.device)'
```

Workbench entrypoint (Jupyter on 8888; stop with Ctrl+C):

```bash
podman run --rm -p 8888:8888 quay.io/MY-ORG/my-pytorch-cuda:latest
```

---

## Example 2 — PyTorch + ROCm

**Prereq:** [entitlements](#1-set-up-entitlements) if you pick the AIPCC base.

**Wizard choices:** ROCm 7.14 → PyTorch → AIPCC/ODH base → AIPCC index →
`linux/amd64` (ROCm is typically x86_64-only) → folder `my-pytorch-rocm`.

```bash
./interactive-image-builder.sh
# → creates my-pytorch-rocm/

make build RECIPE=my-pytorch-rocm PLATFORM=linux/amd64 PUSH_IMAGES=no
make validate RECIPE=my-pytorch-rocm
make push RECIPE=my-pytorch-rocm
```

Smoke test:

```bash
podman run --rm --entrypoint python \
  quay.io/MY-ORG/my-pytorch-rocm:latest \
  -c 'import torch; print("torch", torch.__version__, "hip?", getattr(torch.version, "hip", None))'
```

On an AMD GPU host (device flags depend on your ROCm/container toolkit setup):

```bash
podman run --rm --device /dev/kfd --device /dev/dri --group-add video --entrypoint python \
  quay.io/MY-ORG/my-pytorch-rocm:latest \
  -c 'import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no gpu")'
```

---

## Example 3 — TrustyAI + CPU

**Prereq:** [entitlements](#1-set-up-entitlements) for the AIPCC base.

**Wizard choices:** CPU → TrustyAI collection → AIPCC base → AIPCC index (recommended) →
folder `my-trustyai`.

Do **not** mix TrustyAI with PyTorch/LLM Compressor in the same image (numpy/pandas ABI).
See [src/collections/README.md](src/collections/README.md).

```bash
./interactive-image-builder.sh
# → creates my-trustyai/

make build RECIPE=my-trustyai PUSH_IMAGES=no
make validate RECIPE=my-trustyai
make push RECIPE=my-trustyai
```

Smoke test (collection validator shipped in the image):

```bash
podman run --rm --entrypoint python \
  quay.io/MY-ORG/my-trustyai:latest \
  /opt/app-root/src/collections/trustyai/validate.py
```

Or a one-liner:

```bash
podman run --rm --entrypoint python \
  quay.io/MY-ORG/my-trustyai:latest \
  -c 'import trustyai, transformers, torch; print("trustyai OK", torch.__version__)'
```

---

## Example 4 — LLM Compressor + CUDA

**Prereq:** [entitlements](#1-set-up-entitlements) for the AIPCC base.

**Wizard choices:** CUDA 13.0 → LLM Compressor collection → AIPCC base → AIPCC index →
folder `my-llmcompressor-cuda`.

```bash
./interactive-image-builder.sh
# → creates my-llmcompressor-cuda/

make build RECIPE=my-llmcompressor-cuda PUSH_IMAGES=no
make validate RECIPE=my-llmcompressor-cuda
make push RECIPE=my-llmcompressor-cuda
```

Smoke test:

```bash
podman run --rm --entrypoint python \
  quay.io/MY-ORG/my-llmcompressor-cuda:latest \
  /opt/app-root/src/collections/llmcompressor/validate.py
```

```bash
podman run --rm --entrypoint python \
  quay.io/MY-ORG/my-llmcompressor-cuda:latest \
  -c 'import llmcompressor, torch; print("llmcompressor OK", torch.__version__, "cuda?", torch.cuda.is_available())'
```

---

## Shared tips

| Goal | Command |
|------|---------|
| List generated folders | `make list` |
| List package collections | `make collections` |
| Build without push | `make build RECIPE=<name> PUSH_IMAGES=no` |
| Override arch | `make build RECIPE=<name> PLATFORM=linux/arm64` |
| Import in OpenShift AI | Settings → Workbench images → Import → `quay.io/MY-ORG/<repo>:<tag>` |

**Pipeline runtime:** same image digest; Elyra should invoke `entrypoint.sh runtime`
(see `src/bin/entrypoint.sh`). Local check:

```bash
podman run --rm --entrypoint /opt/app-root/bin/entrypoint.sh \
  quay.io/MY-ORG/my-pytorch-cuda:latest \
  runtime --help || true
```

**Base images:** AIPCC repos do not publish `:latest`. Pins live in
`src/defaults/bases.env` (aligned with `jupyter/*/build-args/konflux.*.conf`).
Refresh when those pins move.

**Subscription:** Quay pull access ≠ RHEL entitlements. If `dnf` fails with
“Unable to read consumer identity” / “no enabled repositories”, re-do
[step 1](#1-set-up-entitlements). `openshift-clients` comes from the public
OpenShift mirror (`src/repos/openshift-clients.repo`), not BaseOS — that is
copied into each recipe automatically. Escape hatches: CentOS Stream (ODH)
base in the wizard, or
`BUILD_ARGS='--build-arg INSTALL_OS_PACKAGES=false'` for a pip-only PoC.

## Package collections (item 3)

Curated package lists live under `src/collections/`. Each collection has an **ABI
ceiling** (`constraints`). The wizard installs **one** collection per image.
TrustyAI and PyTorch/LLM Compressor **conflict** (e.g. numpy 1.x vs 2.x) — generate
two images or use an isolated venv.

| Step | How |
|------|-----|
| Discover | `make collections` / `src/collections/*/collection.toml` |
| Select | Wizard stack: TrustyAI or LLM Compressor |
| Install | `make build` → `pip`/`uv` from index (unpinned within constraints) |
| Validate | `make validate RECIPE=…` |

Details: [src/collections/README.md](src/collections/README.md).

## Wizard choices

1. Accelerator (CPU / CUDA 13 / 12.9 / ROCm)  
2. Stack (Minimal / PyTorch / **TrustyAI** / **LLM Compressor**)  
3. Base (CentOS Stream ODH vs AIPCC RHEL)  
4. Index (PyPI vs AIPCC — defaults to AIPCC for collections)  
5. Platform  
6. Quay org → repo → tag → folder name  

## Ticket checklist

| Item | Covered by |
|------|------------|
| §2 Custom CUDA/ROCm images | Wizard + `src/` + `make build/push` |
| §3 TrustyAI collection | `src/collections/trustyai` |
| §3 LLM Compressor collection | `src/collections/llmcompressor` |
| Discovery / selection / install / validate | `make collections`, wizard, build, `make validate` |

## Support boundary

Customer-built images and collections are **not** Red Hat OOTB workbenches.
Edit `src/collections/` to change curated sets for new generations.
