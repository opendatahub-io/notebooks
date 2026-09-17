# Creating Isolated Virtual Environments in OOTB Notebook Images

This guide shows how to create and use a **customer-managed Python virtual
environment** inside an out-of-the-box (OOTB) Red Hat OpenShift AI workbench
image, install packages from PyPI, and avoid common pitfalls around binary
compatibility.

## Why a Separate Virtual Environment?

Every OOTB workbench image ships with a pre-built virtual environment at
`/opt/app-root`. That environment is curated by Red Hat: its packages come
from the AIPCC (AI Platform Content Collection) index and are compiled
against the specific system libraries, accelerator SDK, and Python version
bundled in the image.

When you need packages that are **not** in the OOTB environment, or need
**different versions** of packages that are, a separate virtual environment
keeps your additions isolated from the pre-built stack. This avoids
overwriting validated packages and makes your custom environment easy to
recreate.

## Quick Reference

| Item | OOTB environment | Customer-managed venv |
|------|------------------|-----------------------|
| Location | `/opt/app-root` | `~/envs/my-venv` (your choice) |
| Package source | AIPCC index (baked into image) | PyPI or your own index |
| System library linkage | Matched to image RPMs | Must match at runtime |
| Support | Fully supported by Red Hat | Customer responsibility |
| Recreatable across restarts? | Yes (image rebuild) | Only if you script it |

## Prerequisites

- An OOTB workbench running on OpenShift AI (Jupyter or Code-Server).
- A persistent volume mounted at the default home directory (`/opt/app-root/src`).
  OpenShift AI workbenches configure this automatically.

## Step-by-Step: Create and Activate an Isolated venv

### 1. Open a Terminal

In JupyterLab, open **File > New > Terminal**. In Code-Server, use the
integrated terminal.

### 2. Create the Virtual Environment

Create a new venv in your home directory. The `--system-site-packages` flag
is **intentionally omitted** so the new environment starts clean and does not
inherit packages from the OOTB `/opt/app-root` environment.

```bash
python3 -m venv ~/envs/my-venv
```

> **Why not `--system-site-packages`?** Including it would make every AIPCC
> package visible inside your venv. If you then install a PyPI version of the
> same package, the two builds can conflict at the shared-library level (see
> [Anti-Patterns](#anti-patterns-do-not-do-this) below). A clean venv avoids
> this class of problems entirely.

### 3. Activate the Environment

```bash
source ~/envs/my-venv/bin/activate
```

Your shell prompt changes to show `(my-venv)`. All subsequent `pip install`
commands target this environment.

### 4. Verify the Active Environment

```bash
which python
```

Expected output:

```text
/opt/app-root/src/envs/my-venv/bin/python
```

```bash
pip config get global.index-url 2>/dev/null || echo "(no custom index configured)"
```

Expected output:

```text
(no custom index configured)
```

This confirms pip is **not** pointed at the AIPCC index. Packages will
resolve from `https://pypi.org/simple/` by default.

### 5. Install Packages from PyPI

```bash
pip install pandas scikit-learn matplotlib
```

### 6. Register a Jupyter Kernel (Optional)

To use your venv from a JupyterLab notebook cell instead of only from the
terminal:

```bash
pip install ipykernel
python -m ipykernel install --user --name my-venv --display-name "Python (my-venv)"
```

Refresh the JupyterLab launcher to see the new kernel.

### 7. Deactivate When Done

```bash
deactivate
```

This returns you to the OOTB `/opt/app-root` environment.

## Understanding Package Indexes

### AIPCC Index (Red Hat)

The OOTB environment uses a **Red Hat-managed Python package index** provided
by the AIPCC pipeline. Packages on this index are:

- Compiled against the specific system libraries (glibc, OpenBLAS, HDF5, etc.)
  installed in the image via RPM.
- Built for the specific accelerator SDK version in the image (CUDA toolkit,
  ROCm, or CPU-only).
- Tested as a coherent set for the RHOAI release.

The index URL is baked into the image's `pip.conf` and `uv.toml` at
`/opt/app-root/`. You do not need to (and should not) configure it manually
for the OOTB environment.

### PyPI (Community)

`https://pypi.org/simple/` is the default Python package index. Packages on
PyPI are compiled by their upstream maintainers against a broad set of manylinux
standards. They are **not** guaranteed to link against the same shared-library
versions that the OOTB image provides.

### When to Use Which

| Scenario | Recommended index |
|----------|-------------------|
| Working inside the OOTB `/opt/app-root` environment | AIPCC (already configured) |
| Working inside your own venv (this guide) | PyPI (default) |
| Need a package that exists on AIPCC but not PyPI | See [Using the AIPCC Index in Your venv](#using-the-aipcc-index-in-your-venv-advanced) |

## Accelerator-Specific Considerations

### CPU Images

CPU-only images (`jupyter-minimal-cpu`, `jupyter-datascience-cpu`,
`codeserver-minimal-cpu`) have no GPU SDK. PyPI packages that ship
CPU-only wheels (the common case for NumPy, Pandas, scikit-learn, etc.)
generally work without issues in a customer-managed venv.

**[NEEDS VALIDATION]** Pure-Python packages and packages shipping manylinux
wheels for x86_64 should install and run correctly. Packages that compile
native extensions at install time require the development headers already
present in the image (gcc, gcc-c++, and common libraries are pre-installed).

### CUDA Images

CUDA images (`jupyter-minimal-cuda`, `jupyter-pytorch-cuda`, etc.) include a
specific CUDA toolkit version (e.g. CUDA 13.0) and cuDNN. When installing
GPU-accelerated packages from PyPI into your venv:

1. **Match the CUDA major version.** PyPI wheels for PyTorch, TensorFlow, and
   similar frameworks are compiled against a specific CUDA version. If the
   wheel expects CUDA 12.x but the image provides CUDA 13.0, the package
   may fail to load GPU libraries at runtime.

2. **Check the wheel's CUDA requirement.** PyTorch publishes wheels per CUDA
   version on its own index (`https://download.pytorch.org/whl/`). Use the
   variant that matches the image's CUDA version.

3. **cuDNN and NCCL versions matter.** These libraries are bundled in the
   image. A PyPI wheel that bundles its own cuDNN may conflict with the
   image's version.

To check the CUDA version inside a running workbench:

```bash
nvcc --version 2>/dev/null || cat /usr/local/cuda/version.txt 2>/dev/null || echo "CUDA not found"
```

**[NEEDS VALIDATION]** The exact CUDA toolkit path and version detection
method may vary between AIPCC base image versions. Confirm with
`ls /usr/local/cuda*/` inside the running image.

### ROCm Images

ROCm images (`jupyter-minimal-rocm`, `jupyter-pytorch-rocm`, etc.) include
AMD's ROCm SDK. The same version-matching considerations apply:

1. **Match the ROCm version.** PyTorch publishes ROCm-specific wheels on its
   own index. Use the variant matching the image's ROCm version.

2. **ROCm SDK paths.** ROCm libraries are typically at `/opt/rocm`. Confirm
   the version:

```bash
cat /opt/rocm/.info/version 2>/dev/null || echo "ROCm version file not found"
```

**[NEEDS VALIDATION]** ROCm version detection path may differ between AIPCC
base image versions.

3. **HIP compiler compatibility.** Packages that compile HIP kernels at
   install time need the ROCm development tools in the image.

### Summary: Accelerator Compatibility Matrix

| Image variant | Safe to install from PyPI | Caution required |
|---------------|--------------------------|------------------|
| CPU | Pure-Python, manylinux wheels | Packages compiling against uncommon system libs |
| CUDA | Pure-Python, CPU-only wheels | GPU wheels (must match CUDA version) |
| ROCm | Pure-Python, CPU-only wheels | GPU wheels (must match ROCm version) |

## Support Boundaries

### What Red Hat Supports

- The **OOTB virtual environment** at `/opt/app-root` and all packages
  installed in it from the AIPCC index.
- The **base operating system**, system libraries, and accelerator SDK
  (CUDA/ROCm) bundled in the image.
- The **workbench platform integration**: Jupyter/Code-Server startup, OAuth
  proxy, persistent storage, idle culling.

### What Is Customer Responsibility

- Any **customer-created virtual environment** (like the one in this guide)
  and all packages installed into it.
- **Compatibility** between PyPI packages and the image's system libraries
  or accelerator SDK.
- **Persistence** of the virtual environment across workbench restarts.
  The venv on a persistent volume survives pod restarts, but if the
  workbench image is upgraded (e.g. from RHOAI 3.5 to 3.6), system
  library versions may change, which can break compiled packages in the
  customer venv. In that case, recreate the venv.
- **Reproducing the environment.** Red Hat recommends keeping a
  `requirements.txt` so the venv can be recreated after image upgrades.

### Grey Area: System Libraries

Packages installed from PyPI into your venv may dynamically link against
system libraries provided by the image (glibc, OpenSSL, libstdc++, zlib,
etc.). These linkages are supported only in the sense that Red Hat supports
the system libraries themselves. If a PyPI package requires a system library
version that differs from what the image provides, that is a customer
environment issue, not an image defect.

## Using the AIPCC Index in Your venv (Advanced)

In some cases you may want to install a package from the AIPCC index into your
customer-managed venv. This can be useful when the package is available on
AIPCC but not on PyPI, or when you want binaries compiled against the exact
system libraries in the image.

**[NEEDS VALIDATION]** The AIPCC index is accessible at the URL stored in the
image's pip.conf. To retrieve it:

```bash
grep index-url /opt/app-root/pip.conf
```

Expected output (example for a CPU image):

```text
index-url = https://packages.redhat.com/api/pypi/public-rhai/rhoai/<channel>/simple/
```

To install a single package from the AIPCC index into your venv:

```bash
source ~/envs/my-venv/bin/activate
pip install --index-url "$(grep index-url /opt/app-root/pip.conf | awk '{print $3}')" <package-name>
```

> **Warning:** This is an advanced technique. The AIPCC index URL is specific
> to the image variant (CPU, CUDA, ROCm) and RHOAI release. Do not mix
> packages from different AIPCC channels (e.g. installing a CUDA-channel
> package into a venv on a CPU image). See
> [Anti-Patterns](#anti-patterns-do-not-do-this) for details.

## Persisting Your Environment

Since the workbench's home directory (`/opt/app-root/src`) is backed by a
persistent volume, a venv created under `~/envs/` survives pod restarts.
However:

1. **Image upgrades can break the venv.** When the workbench image is updated
   to a new RHOAI release, system libraries and Python patch versions may
   change. Compiled `.so` files in your venv may fail to load. Solution:
   keep a `requirements.txt` and recreate the venv after upgrades.

2. **Export your requirements before upgrading:**

```bash
source ~/envs/my-venv/bin/activate
pip freeze > ~/envs/my-venv-requirements.txt
deactivate
```

3. **Recreate after an image upgrade:**

```bash
rm -rf ~/envs/my-venv
python3 -m venv ~/envs/my-venv
source ~/envs/my-venv/bin/activate
pip install -r ~/envs/my-venv-requirements.txt
```

## Anti-Patterns (Do Not Do This)

### 1. Do Not Mix AIPCC and PyPI Binaries in the Same Environment

**Problem:** The AIPCC index compiles binary wheels against the exact system
library versions in the image (e.g. a specific OpenBLAS, HDF5, or protobuf
`.so`). PyPI wheels are compiled against manylinux standards, which bundle or
expect different library versions. Installing both into the same environment
can cause:

- **Symbol conflicts** at import time (`undefined symbol`, `symbol not found`).
- **Silent numerical errors** if two linear algebra backends (e.g. different
  OpenBLAS builds) are loaded into the same process.
- **Segmentation faults** from ABI mismatches in C extensions.

**Example of what NOT to do:**

```bash
# BAD: Installing numpy from AIPCC (compiled against image's OpenBLAS)
# and then scipy from PyPI (compiled against bundled OpenBLAS) in the
# same environment risks ABI conflicts.
pip install --index-url <AIPCC-URL> numpy
pip install scipy  # from PyPI -- may bundle incompatible OpenBLAS
```

**Safe alternative:** Use one index per environment. The OOTB environment
uses AIPCC exclusively. Your customer venv should use PyPI exclusively (the
default). Only deviate from this if you have validated the specific
combination.

### 2. Do Not Install into the OOTB Environment

```bash
# BAD: This modifies the Red Hat-supported environment
pip install --target /opt/app-root/lib/python3.12/site-packages some-package
```

Installing packages directly into `/opt/app-root` is unsupported and can
break workbench functionality (JupyterLab, Elyra, notebook kernel).
Always use a separate venv.

### 3. Do Not Use `--system-site-packages` with Mixed Indexes

```bash
# BAD: Creates a venv that sees AIPCC packages AND lets you install PyPI
# packages on top -- the mixing problem from anti-pattern 1.
python3 -m venv --system-site-packages ~/envs/mixed-env
```

If you need visibility into AIPCC packages, use the OOTB environment
directly. If you need PyPI packages, use a clean isolated venv.

### 4. Do Not Install CUDA-Variant Packages on a CPU Image (or Vice Versa)

```bash
# BAD: The CPU image has no CUDA libraries; this package cannot run.
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

Match the package's accelerator variant to the image you are running on.
CPU images should use CPU-only wheels; CUDA images should use CUDA-matched
wheels.

## Complete Example: Data Analysis venv on a CPU Image

This end-to-end example creates a venv for data analysis work, registers it
as a Jupyter kernel, and prepares it for reproducibility.

```bash
# Create and activate
python3 -m venv ~/envs/data-analysis
source ~/envs/data-analysis/bin/activate

# Install packages from PyPI
pip install pandas matplotlib seaborn scikit-learn jupyterlab-widgets ipykernel

# Register as a Jupyter kernel
python -m ipykernel install --user --name data-analysis --display-name "Python (Data Analysis)"

# Save requirements for reproducibility
pip freeze > ~/envs/data-analysis-requirements.txt

# Deactivate
deactivate
```

After running this, restart the JupyterLab launcher and select the
**Python (Data Analysis)** kernel in a new notebook.

## Complete Example: PyTorch from PyPI on a CUDA Image

**[NEEDS VALIDATION]** This example installs PyTorch from PyPI's CUDA-specific
index into a clean venv on a CUDA 13.0 image. The CUDA version in the pip
index URL must match the image's CUDA version.

```bash
# Check the image's CUDA version first
nvcc --version 2>/dev/null | grep "release" || echo "Check /usr/local/cuda/version.txt"

# Create and activate
python3 -m venv ~/envs/pytorch-custom
source ~/envs/pytorch-custom/bin/activate

# Install PyTorch matching the image's CUDA version
# Replace cu130 with the appropriate CUDA version tag
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# Verify GPU access
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# Register kernel and save requirements
pip install ipykernel
python -m ipykernel install --user --name pytorch-custom --display-name "Python (PyTorch Custom)"
pip freeze > ~/envs/pytorch-custom-requirements.txt

deactivate
```

## Troubleshooting

### "Permission denied" when Creating a venv

The workbench runs as a non-root user (UID 1001). Create your venv under the
home directory (`~/envs/`) which is on the persistent volume and writable.
Do not attempt to create environments under `/opt/app-root` or other
system paths.

### Import Errors After Image Upgrade

If you see errors like `ImportError: libfoo.so.2: cannot open shared object
file` after an image upgrade, the system libraries have changed. Recreate
your venv from your saved `requirements.txt`.

### Kernel Not Appearing in JupyterLab

After running `ipykernel install --user`, refresh the browser page. If the
kernel still does not appear, verify the kernel spec was created:

```bash
jupyter kernelspec list
```

Look for your kernel name in the output.

### Package Fails to Install (Missing Compiler or Headers)

The OOTB images include `gcc`, `gcc-c++`, and common development libraries.
If a package requires a header file that is not present, you cannot install
it without building a custom image. File a feature request if the missing
dependency is commonly needed.

## Further Reading

- [ARCHITECTURE.md](../ARCHITECTURE.md) -- Image hierarchy and build system
  overview.
- [docs/subscribed-builds.md](subscribed-builds.md) -- How AIPCC base images
  and subscriptions work (for image builders, not end users).
- [docs/workbenches.md](workbenches.md) -- Workbench image naming and
  variants.
