# PyPI-Enabled Minimal Workbench Images — BU Demo Cheatsheet

## What these images are

Minimal workbench images (Jupyter + CodeServer) on RHEL 9 / UBI9 base, configured
to use **PyPI** as the default pip index instead of the AIPCC/Red Hat Python index.

No ML frameworks pre-installed. Users `pip install` what they need at runtime.

## Available images

| Image | quay.io | Use for |
|-------|---------|---------|
| JupyterLab | `quay.io/jdanek/jupyter-minimal-cpu-pypi:spike` | Notebook workflows |
| CodeServer | `quay.io/jdanek/codeserver-cpu-pypi:spike3` | VS Code in browser |

Both are CPU-only base images. GPU frameworks (PyTorch, TensorFlow) bundle their
own CUDA/ROCm runtime and work without CUDA RPMs in the image.

## Quick start on OpenShift

Deploy imagestreams into your namespace (one command):

```bash
oc apply -n <your-namespace> -f jupyter/minimal/ubi9-python-3.12-pypi/imagestreams.yaml
```

Then in the RHOAI dashboard:
1. Create a workbench using "Jupyter Minimal PyPI (CPU)" or "CodeServer PyPI (CPU)"
2. Optionally request a GPU
3. Open terminal, install what you need

## Installing PyTorch (CUDA)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

Verify GPU:

```python
import torch
print("torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    arch = getattr(props, 'gcnArchName', f"SM {props.major}.{props.minor}")
    print(f"Device: {props.name} ({arch})")
    print(f"Memory: {props.total_memory // 1024**2} MB, CUs/SMs: {props.multi_processor_count}")
```

**Note:** If using PyTorch < 2.6, the `torch.accelerator` API doesn't exist yet.
Use the legacy device detection:

```python
device = "cuda" if torch.cuda.is_available() else "cpu"
```

If you get `AttributeError: module 'torch' has no attribute 'accelerator'`,
either upgrade torch (`pip install --upgrade torch`) or use the legacy pattern above.

## Installing PyTorch (ROCm)

ROCm wheels are hosted on PyTorch's custom index (not on default PyPI):

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm7.1/
```

Unlike CUDA, there are no granular `nvidia-*` style ROCm PyPI packages.
The ROCm runtime is bundled inside the torch wheel itself (~3GB download).

Verify GPU (same commands as CUDA -- ROCm uses the CUDA API):

```python
import torch
print("torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    # ROCm reports "AMD Radeon Graphics" as name; gcnArchName shows the real arch (e.g. gfx942 = MI300X)
    print(f"Device: {props.name} ({props.gcnArchName})")
    print(f"Memory: {props.total_memory // 1024**2} MB, CUs: {props.multi_processor_count}")
```

## Installing TensorFlow (CUDA)

```bash
pip install "tensorflow[and-cuda]"
```

The `[and-cuda]` extra pulls NVIDIA CUDA libraries from PyPI automatically.

Verify GPU:

```python
import tensorflow as tf
print("TF version:", tf.__version__)
print("Built with CUDA:", tf.test.is_built_with_cuda())
gpus = tf.config.list_physical_devices('GPU')
print("GPUs:", gpus)
if gpus:
    print("GPU name:", gpus[0].name)
```

## Installing TensorFlow (ROCm)

TensorFlow ROCm support requires system-level ROCm installation — it cannot
be installed purely from PyPI like the CUDA variant. The `tensorflow-rocm`
package on PyPI expects ROCm to be pre-installed on the host.

For ROCm + TensorFlow, use AIPCC-based (secure) images instead.

## CUDA compiler (nvcc) from PyPI

If you need to compile custom CUDA kernels (e.g., for vLLM's FlashInfer JIT,
custom torch extensions):

```bash
pip install nvidia-cuda-nvcc
```

Most users don't need this — `torch.compile` uses Triton (Python-based, no nvcc).

## Known issues and workarounds

### TensorBoard fails with `No module named 'pkg_resources'`

Python 3.12 dropped bundled `setuptools`. TensorBoard still depends on it.

```bash
pip install "setuptools<70.0.0"
```

Versions 70.0+ removed `pkg_resources`. Upgrading TensorBoard alone doesn't
fix it because TensorFlow pins the TensorBoard version.

### No `rocm-smi` / `rocminfo` on ROCm clusters

The PyTorch ROCm wheel bundles only runtime libs, not the AMD diagnostic CLI tools
(`rocm-smi`, `rocminfo`). These come from AMD's ROCm RPM repos, not UBI9 or PyPI.
Use `torch.cuda.get_device_properties(0)` to get GPU arch, memory, and CU count.
For full GPU monitoring, the tools need to be pre-installed in the image or
available on the host node.

### pip installs don't survive pod restarts

Packages installed at runtime are lost when the OpenShift pod restarts (node
drain, scale-down, OOM kill). Options:

- Mount a PVC on `/opt/app-root` for persistence
- Save `requirements.txt` to PVC, re-run `pip install -r` after restart
- Build a custom image with your packages baked in

### torch.accelerator not found

PyTorch < 2.6 doesn't have `torch.accelerator`. Use:

```python
device = "cuda" if torch.cuda.is_available() else "cpu"
```

## What's NOT in these images

- No torch, numpy, pandas, scipy, scikit-learn
- No CUDA/ROCm RPMs (torch bundles its own)
- No Red Hat supply chain guarantees on user-installed packages
- This is the "community" tier — user accepts responsibility

## What IS in these images

- Python 3.12 (UBI9)
- JupyterLab 4.5.x or CodeServer 4.106.3
- pip configured to use `https://pypi.org/simple/`
- Standard RHEL 9 system libraries
- `gcc`, `make` (for building C extensions from source if needed)

## CUDA ABI — why CPU base is fine

PyTorch and TensorFlow wheels from PyPI bundle their own CUDA runtime
libraries. They don't depend on system-installed CUDA RPMs. This is the
same configuration that worked in RHOAI through 3.3.

RPM-installed CUDA and PyPI-bundled CUDA coexist without conflicts.

## Architecture support

Currently amd64 only. arm64 is feasible (UBI9 and code-server RPMs both
support it). IBM ppc64le/s390x would need investigation.
