# Creating Isolated Virtual Environments in OOTB Notebook Images

This guide explains the Python environments in an out-of-the-box (OOTB) Red
Hat OpenShift AI workbench image and shows how to create an optional
**customer-managed Python virtual environment**. It covers installing user
packages from PyPI while preserving the image's JupyterLab installation and
avoiding common binary-compatibility pitfalls.

## Proposed Image Architecture

The proposed dual-venv architecture is:

- `/opt/jupyterlab` would be the internal JupyterLab environment. It would
  contain JupyterLab, its extensions, and their dependencies. Users would not
  install packages into this environment.
- `/opt/app-root` would be the user-facing environment and the default
  notebook kernel environment. It would contain the image-provided
  `ipykernel`, and user package installs would be supported there.
- Startup scripts and Jupyter server commands would invoke
  `/opt/jupyterlab/bin/jupyter` directly, while kernels would execute with the
  user-facing environment's Python.
- `JUPYTER_PATH=/opt/app-root/share/jupyter` would allow JupyterLab to discover
  kernels registered in the user-facing environment.

The image-provided default kernel would be registered at
`/opt/app-root/share/jupyter/kernels/python3/kernel.json` and run with
`/opt/app-root/bin/python`. Customer kernels would be additional kernels and
should point to their own customer-managed venv. They should be registered
under `/opt/app-root/share/jupyter`, the kernelspec location exposed to the
proposed JupyterLab environment.

The customer-managed venv described below is optional. Use it when you want a
reproducible, separately managed environment under the persistent home volume;
otherwise, installing a package into the active `/opt/app-root` environment
would be the supported user-facing workflow.

> [!IMPORTANT]
> This is a proposed target architecture, not a claim about every currently
> published workbench image. Currently published images use a single Python
> environment. The `/opt/jupyterlab` and `/opt/app-root` split is the proposed
> change described by this guide. Implementing it requires updating the
> startup scripts and related commands to use `/opt/jupyterlab` explicitly;
> it should not depend on an `/opt/app-root/bin/jupyter` symlink.

> [!NOTE]
> The proposed dual-venv runtime implementation uses a `.pth` bridge from
> `/opt/app-root` to `/opt/jupyterlab` so the pipeline bootstrapper can import
> execution dependencies while `/opt/app-root` is incomplete. This is a
> workaround, not the desired isolation model. The correct long-term fix is to
> make the user-facing `/opt/app-root` environment complete for its workload
> rather than exposing the internal JupyterLab environment through `sys.path`.
> The available RHOAI 3.6 EA1 runtime tags did not contain this PR-specific
> bridge, so the bridge itself could not be runtime-tested on this host.

> [!NOTE]
> The proposed dual-venv layout applies to the image variants and
> architectures that include JupyterLab. Baseline images on `ppc64le` and `s390x` retain their
> existing single-environment layout, so `/opt/app-root` contains the full
> image stack there.

## Why a Separate Virtual Environment?

The proposed workbench layout provides an image-managed user-facing Python
environment at `/opt/app-root`. In the proposed dual-venv layout, the JupyterLab
stack would be separate and live at `/opt/jupyterlab`. Image-provided packages
would be curated by Red Hat and compiled against the specific system libraries,
accelerator SDK, and Python version bundled in the image.

Installing packages into the proposed `/opt/app-root` environment would be
supported for user workloads. When you need stronger isolation, different
package versions, or a reproducible
environment, a separate venv keeps those additions independent from the
default user environment and makes them easier to recreate.

## Quick Reference

| Item | JupyterLab environment | User-facing environment | Customer-managed venv |
|------|------------------------|-------------------------|-----------------------|
| Location | `/opt/jupyterlab` | `/opt/app-root` | `~/envs/my-venv` (your choice) |
| Purpose | JupyterLab and its dependencies | Default kernel and user installs | Optional isolated workload |
| Package source | Image-managed AIPCC packages | Image baseline plus supported user installs | PyPI or your own index |
| Support | Red Hat-managed | User-facing and supported | Customer responsibility |
| Recreatable across restarts? | Image rebuild | Image rebuild | Only if you script it |

## Prerequisites

- An OOTB workbench running on OpenShift AI (Jupyter or Code-Server).
- A persistent volume mounted at the default home directory (`/opt/app-root/src`).
  OpenShift AI workbenches configure this automatically.

## Proposed Supported Default Workflow

In the proposed layout, `/opt/app-root` is the user-facing environment. If no
customer-managed venv is activated, `python` and `pip` target `/opt/app-root`,
and installing a package there is supported:

```bash
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url https://pypi.org/simple <package-name>
```

This would not install anything into `/opt/jupyterlab`; JupyterLab would use
its internal environment while notebook kernels would use `/opt/app-root`.

> [!IMPORTANT]
> Use a customer-managed venv when you need a reproducible environment or
> want to avoid changing the default `/opt/app-root` kernel environment. Never
> install user packages directly into `/opt/jupyterlab`.

## Step-by-Step: Create and Activate an Isolated venv

### 1. Open a Terminal

In JupyterLab, open **File > New > Terminal**. In Code-Server, use the
integrated terminal.

### 2. Create the Virtual Environment

Create a new venv in your home directory. The `--system-site-packages` flag
is **intentionally omitted** so the new environment starts clean and does not
inherit packages from the user-facing `/opt/app-root` environment.

```bash
unset PYTHONPATH
python3 -m venv ~/envs/my-venv
```

> [!NOTE]
> **Why not `--system-site-packages`?** It would expose the packages installed
> in the user-facing `/opt/app-root` environment inside this venv. On runtime
> images, that can also expose the temporary `.pth` bridge to JupyterLab
> packages. A clean venv avoids coupling the customer environment to either
> image-managed environment.

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
pip config debug
env | grep '^PIP_' || true
```

`PIP_CONFIG_FILE`, `PIP_INDEX_URL`, and `PIP_EXTRA_INDEX_URL` may be inherited
from the workbench image. Do not rely on `pip config get` alone to determine
which index will be used. The commands below pass the PyPI index explicitly
and remove any extra index for each installation.

### 5. Install Packages from PyPI

```bash
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url https://pypi.org/simple pandas scikit-learn matplotlib
```

The command-line `--index-url` takes precedence over inherited pip
configuration. Keeping `PIP_EXTRA_INDEX_URL` unset prevents dependency
resolution from silently combining PyPI with another index.

### 6. Register a Jupyter Kernel (Optional)

To use your venv from a JupyterLab notebook cell instead of only from the
terminal:

```bash
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url https://pypi.org/simple ipykernel
python -m ipykernel install --prefix /opt/app-root --name my-venv \
  --display-name "Python (my-venv)"
```

Do not use `--user` here. It installs the kernelspec under the home-directory
Jupyter data path, which is not the explicit kernelspec path used by the
proposed dual-venv startup configuration.

Because the workbench may export `PYTHONPATH`, edit the generated
`kernel.json` so the kernel removes it before starting. Find the file with
`jupyter kernelspec list`; its `argv` must begin like this:

```json
"argv": [
  "env", "-u", "PYTHONPATH",
  "/opt/app-root/src/envs/my-venv/bin/python",
  "-m", "ipykernel_launcher", "-f", "{connection_file}"
]
```

Apply the same `argv` change to every customer kernel registered below,
preserving that environment's existing Python path.

Refresh the JupyterLab launcher to see the new kernel.

### 7. Deactivate When Done

```bash
deactivate
```

This returns you to the user-facing `/opt/app-root` environment. JupyterLab
continues to run from its separate `/opt/jupyterlab` environment.

## Understanding Package Indexes

### AIPCC Index (Red Hat)

Image-managed packages in the OOTB environments use a **Red Hat-managed
Python package index** provided by the AIPCC pipeline. Packages on this index
are:

- Compiled against the specific system libraries (glibc, OpenBLAS, HDF5, etc.)
  installed in the image via RPM.
- Built for the specific accelerator SDK version in the image (CUDA toolkit,
  ROCm, or CPU-only).
- Tested as a coherent set for the RHOAI release.

The index URL is baked into the image's `pip.conf` and `uv.toml` at
`/opt/app-root/`. The image uses it for image-managed packages. User installs
into `/opt/app-root` are supported, but this guide selects PyPI explicitly for
the examples below so the source is unambiguous.

### PyPI (Community)

`https://pypi.org/simple/` is the default Python package index. Packages on
PyPI are compiled by their upstream maintainers against a broad set of manylinux
standards. They are **not** guaranteed to link against the same shared-library
versions that the OOTB image provides.

### When to Use Which

| Scenario | Recommended index |
|----------|-------------------|
| Working inside the user-facing `/opt/app-root` environment | PyPI explicitly for customer packages; the image baseline remains AIPCC-managed |
| Working inside your own venv (this guide) | PyPI (default) |
| Need a package that exists on AIPCC but not PyPI | See [Using the AIPCC Index in Your venv](#using-the-aipcc-index-in-your-venv-advanced) |

## Accelerator-Specific Considerations

### CPU Images

CPU-only images (`jupyter-minimal-cpu`, `jupyter-datascience-cpu`,
`codeserver-minimal-cpu`) have no GPU SDK. PyPI packages that ship
CPU-only wheels (the common case for NumPy, Pandas, scikit-learn, etc.)
generally work without issues in a customer-managed venv.

On the x86_64 RHOAI 3.6 EA1 CPU image, the guide's clean venv successfully
installed and imported pandas, scikit-learn, matplotlib, and ipykernel from
PyPI. Pure-Python packages and packages shipping manylinux wheels for x86_64
therefore work as documented on that image. Packages that compile native
extensions at install time still require the development headers present in
the particular image.

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

The CUDA 13.0 image validated above reports its version through `nvcc`.
`/usr/local/cuda/version.txt` was not present in that image, so the fallback
prints `CUDA not found` when `nvcc` is hidden. Other AIPCC base-image versions
may provide a version file at a different path; inspect `/usr/local/cuda*/`
before relying on the fallback for a new image variant.

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

The available ROCm image reports version `7.1.1` from
`/opt/rocm/.info/version`. Other AIPCC base-image versions may use a different
version path, so verify the file when introducing a new ROCm variant.

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

- The **user-facing environment** at `/opt/app-root`, including the image
  baseline, default kernel, and its integration with JupyterLab.
- The internal JupyterLab environment at `/opt/jupyterlab` and its
  image-provided packages.
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

The AIPCC index URL in the validated CPU image's `pip.conf` returned HTTP 200
and is accessible from the image. The URL is release- and accelerator-specific;
retrieve it rather than copying a value between image variants:

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
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url "$(grep index-url /opt/app-root/pip.conf | awk '{print $3}')" <package-name>
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
unset PYTHONPATH
python3 -m venv ~/envs/my-venv
source ~/envs/my-venv/bin/activate
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url https://pypi.org/simple \
  -r ~/envs/my-venv-requirements.txt
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
pip install --index-url https://pypi.org/simple scipy  # may bundle incompatible OpenBLAS
```

**Safe alternative:** Use one index per customer environment. Use the
user-facing `/opt/app-root` environment for supported user installs, or use a
customer venv with the explicit PyPI commands in this guide. Only combine
indexes in one environment after validating the specific combination.

### 2. Do Not Modify the Internal JupyterLab Environment

```bash
# BAD: This modifies the image-managed JupyterLab environment
pip install --target /opt/jupyterlab/lib/python3.12/site-packages some-package
```

Installing packages directly into `/opt/jupyterlab` is unsupported. Install
user packages into the user-facing `/opt/app-root` environment, or use a
customer-managed venv when you need stronger isolation and reproducibility.

### 3. Do Not Use `--system-site-packages` with Mixed Indexes

```bash
# BAD: Creates a venv that sees AIPCC packages AND lets you install PyPI
# packages on top -- the mixing problem from anti-pattern 1.
unset PYTHONPATH
python3 -m venv --system-site-packages ~/envs/mixed-env
```

If you need the image-provided baseline, use `/opt/app-root` directly. If you
need PyPI packages isolated from that baseline, use a clean customer venv.

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
unset PYTHONPATH
python3 -m venv ~/envs/data-analysis
source ~/envs/data-analysis/bin/activate

# Install packages from PyPI
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url https://pypi.org/simple \
  pandas matplotlib seaborn scikit-learn jupyterlab-widgets ipykernel

# Register as a Jupyter kernel
python -m ipykernel install --prefix /opt/app-root --name data-analysis \
  --display-name "Python (Data Analysis)"
# Edit the generated kernel.json: prepend "env", "-u", "PYTHONPATH" to argv.

# Save requirements for reproducibility
pip freeze > ~/envs/data-analysis-requirements.txt

# Deactivate
deactivate
```

After running this, restart the JupyterLab launcher and select the
**Python (Data Analysis)** kernel in a new notebook.

## Complete Example: PyTorch from PyPI on a CUDA Image

The CUDA 13.0 image resolved `torch`, `torchvision`, and `torchaudio` from
PyTorch's `cu130` index in a clean venv. The CUDA version in the pip index URL
must match the image's CUDA version.

> [!WARNING]
> The validation host has no NVIDIA GPU, so `torch.cuda.is_available()` could
> not be validated there. Run the final GPU-access check on a workbench with a
> supported NVIDIA device.

```bash
# Check the image's CUDA version first
nvcc --version 2>/dev/null || \
  cat /usr/local/cuda/version.txt 2>/dev/null || \
  echo "CUDA not found"

# Create and activate
unset PYTHONPATH
python3 -m venv ~/envs/pytorch-custom
source ~/envs/pytorch-custom/bin/activate

# Install PyTorch matching the image's CUDA version
# Replace cu130 with the appropriate CUDA version tag
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# Verify GPU access
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# Register kernel and save requirements
env -u PIP_EXTRA_INDEX_URL \
  python -m pip install --index-url https://pypi.org/simple ipykernel
python -m ipykernel install --prefix /opt/app-root --name pytorch-custom \
  --display-name "Python (PyTorch Custom)"
# Edit the generated kernel.json: prepend "env", "-u", "PYTHONPATH" to argv.
pip freeze > ~/envs/pytorch-custom-requirements.txt

deactivate
```

## Troubleshooting

### "Permission denied" when Creating a venv

The workbench runs as a non-root user (UID 1001). Create customer-managed
venvs under the home directory (`~/envs/`), which is on the persistent volume
and writable. Do not create a nested venv under `/opt/app-root` or
`/opt/jupyterlab`; use `/opt/app-root` directly for the supported default user
workflow.

### Import Errors After Image Upgrade

If you see errors like `ImportError: libfoo.so.2: cannot open shared object
file` after an image upgrade, the system libraries have changed. Recreate
your venv from your saved `requirements.txt`.

### Kernel Not Appearing in JupyterLab

After running `ipykernel install --prefix /opt/app-root`, refresh the browser
page. If the kernel still does not appear, verify the kernel spec was created:

```bash
if [ -x /opt/jupyterlab/bin/jupyter ]; then
  /opt/jupyterlab/bin/jupyter kernelspec list
else
  # Current single-environment images
  jupyter kernelspec list
fi
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
