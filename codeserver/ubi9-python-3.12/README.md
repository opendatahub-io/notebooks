# codeserver/ubi9-python-3.12

Code-server (VS Code in the browser) image with Python 3.12 on UBI 9 for
**RHOAI 2.25** workbenches. Builds are **hermetic**: all RPM, npm, pip, and
generic dependencies are prefetched from committed lockfiles.

Parent overview: [`../README.md`](../README.md).

## Code-server version

| Component | Version |
|-----------|---------|
| code-server | **v4.112.0** (submodule `prefetch-input/code-server`) |
| VS Code | **1.112.0** |
| Node.js (RPM) | **22.22.0** (`nodejs:22` module) |

Hermetic-build customizations live in **`prefetch-input/patches/code-server-v4.112.0/`**
(overlay copied over the submodule at build time). See that directory's
[`README.md`](prefetch-input/patches/code-server-v4.112.0/README.md) for the full
list of overrides, what gets overwritten vs. preserved from older releases, and
how to regenerate lockfiles when bumping code-server again.

Patch scripts (GHA workarounds, offline npm): [`prefetch-input/patches/README.md`](prefetch-input/patches/README.md).

User-facing VS Code extensions (Python, Jupyter) and built-in build `.vsix` files
are documented in [`../Extensions.md`](../Extensions.md).

## Directory layout

```
codeserver/ubi9-python-3.12/
├── Dockerfile.konflux.cpu       # Hermetic multi-stage build (only Dockerfile on 2.25)
├── build-args/
│   ├── cpu.conf                 # Local/GHA (GHA_BUILD=true, public UBI base)
│   └── konflux.cpu.conf         # Konflux Tekton builds
├── pyproject.toml               # Python deps (edit this to change packages)
├── pylock.toml                  # CI lock — public PyPI (bash ci/generate_code.sh)
├── requirements.cpu.txt         # Hermetic pip input for Cachi2/Hermeto
├── uv.lock.d/
│   ├── pylock.cpu.toml          # Offline install lock (RH wheels patched in)
│   └── rh-wheel-only.ref.toml   # RH wheel URLs for ppc64le/s390x overlay
├── prefetch-input/
│   ├── repos/                   # DNF repo definitions (ubi, centos, openshift-clients)
│   ├── rhds/                    # Lockfiles used on rhoai-2.25 (--rhds prefetch)
│   ├── odh/                     # Upstream/midstream reference lockfiles
│   ├── code-server/             # Git submodule (upstream source)
│   └── patches/                 # Offline/GHA overlays + apply-patch.sh
├── utils/                       # User-facing and build-time .vsix extensions
└── nginx/, run-*.sh             # Runtime entrypoints
```

## Build configuration (rhoai-2.25)

| File | Use | Notable settings |
| ---- | --- | ---------------- |
| `build-args/konflux.cpu.conf` | Konflux / `PRODUCT=rhoai` make builds | `BASE_IMAGE=registry.access.redhat.com/ubi9/python-312:latest`, `RELEASE=2.25` |
| `build-args/cpu.conf` | Same base + GHA local builds | Adds `GHA_BUILD=true` for 16GB runner patches |

Make target: `gmake codeserver-ubi9-python-3.12` (uses `Dockerfile.konflux.cpu`).

## Regenerating lockfiles

Python dependencies are declared in [`pyproject.toml`](pyproject.toml). On
**rhoai-2.25** there are two outputs — one for CI/online builds, one for hermetic
Konflux/GHA prefetch.

| File | Purpose | How to regenerate |
| ---- | ------- | ----------------- |
| `pylock.toml` | Online build + `check-generated-code` CI | `bash ci/generate_code.sh` (all images) |
| `uv.lock.d/pylock.cpu.toml` | Hermetic install (RH-wheel patched) | `create-requirements-lockfile.sh` or `prefetch-all.sh` |
| `requirements.cpu.txt` | Cachi2/Hermeto pip prefetch | same as above |
| `prefetch-input/rhds/rpms.lock.yaml` | RPM prefetch | `create-rpm-lockfile.sh` or `prefetch-all.sh --rhds` |
| `prefetch-input/rhds/artifacts.lock.yaml` | Generic artifacts | `create-artifact-lockfile.py` or `prefetch-all.sh --rhds` |
| npm lockfiles under `prefetch-input/patches/` | VS Code / code-server npm | `download-npm.sh` (see [patches README](prefetch-input/patches/code-server-v4.112.0/README.md)) |

**After changing Python deps only:**

```bash
# 1. CI lock (also updates jupyter/runtime if their pyproject.toml changed)
bash ci/generate_code.sh

# 2. Hermetic codeserver locks
uv sync && source .venv/bin/activate
git submodule update --init --recursive prefetch-input/code-server

RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/amd64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds
```

Commit the changed lockfiles; do **not** commit `cachi2/output/` (local prefetch cache).

**After changing RPM or artifact inputs:** edit `prefetch-input/rhds/rpms.in.yaml` or
`artifacts.in.yaml`, then re-run `prefetch-all.sh --rhds` (or the individual generator).

Full details: [scripts/lockfile-generators/README.md](../../scripts/lockfile-generators/README.md#python-lockfiles-on-rhoai-225).

## Hermetic build overview

Every dependency (RPMs, npm packages, Python wheels, generic tarballs) is
prefetched ahead of time and served from a local `cachi2/` directory. No
network access is needed during the image build itself.

There are three ways to build this image:

| Environment | Prefetch method | Build command |
|---|---|---|
| **Local (laptop)** | `prefetch-all.sh --rhds` | `gmake codeserver-ubi9-python-3.12` |
| **GitHub Actions** | Workflow prefetch step (`--rhds`, no subscription) | Push to PR — CI runs automatically |
| **Konflux** | Tekton `prefetch-dependencies` + committed lockfiles | Managed by pipeline |

---

## Building locally

### Prerequisites

| Tool | Purpose |
|------|---------|
| GNU Make 4.0+ (`gmake` on macOS) | Runs the build pipeline |
| `podman` (or `docker`) | Container build engine |
| Repo `.venv` (`uv sync`) | Runs prefetch scripts (`pyyaml`, `packaging`, `uv`) |
| `wget`, `jq`, `hermeto` | Downloads artifacts, npm tarballs, RPMs |
| `yq` | Optional; npm prefetch step |

Set **`RELEASE_PYTHON_VERSION=3.12`** and **`BUILD_ARCH`** when running
`prefetch-all.sh` locally. GHA sets these automatically; without them, pip
prefetch can skip wheels the image still needs at build time. See
[lockfile generators — Local development](../../scripts/lockfile-generators/README.md#local-development).

### Step 1 — Initialize git submodules

The code-server source is vendored as a git submodule:

```bash
git submodule update --init --recursive codeserver/ubi9-python-3.12/prefetch-input/code-server
```

### Step 2 — Prefetch all dependencies

Run from the **repository root**:

```bash
uv sync
source .venv/bin/activate

# Optional: clear pip cache when switching arch or fixing a bad prefetch
# rm -rf cachi2/output/deps/pip

# rhoai-2.25: use --rhds (public UBI + CentOS repos; no subscription required)
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds

# Optional: RHEL subscription RPMs (only if rpms.in.yaml uses redhat.repo)
# RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
#   ./scripts/lockfile-generators/prefetch-all.sh \
#     --component-dir codeserver/ubi9-python-3.12 --rhds \
#     --activation-key my-key --org my-org
```

This single command orchestrates all five lockfile generators:
1. Generic artifacts (GPG keys, VS Code `.vsix`, etc.)
2. Pip wheels (`pylock.toml` → patched `uv.lock.d/pylock.cpu.toml` → `requirements.cpu.txt`)
3. NPM packages (code-server + VS Code extensions)
4. RPMs (gcc, nodejs, nginx, openblas, etc. via Hermeto)
5. Go modules (when Tekton lists gomod prefetch entries)

Lockfiles are organized into variant subdirectories under `prefetch-input/`:

```
prefetch-input/
├── repos/           # shared DNF repo definitions (ubi, centos, epel, rhsm-pulp)
├── odh/             # upstream lockfiles (UBI + CentOS Stream repos)
│   ├── rpms.in.yaml           # references ../repos/*.repo
│   ├── rpms.lock.yaml
│   ├── artifacts.in.yaml
│   └── artifacts.lock.yaml
├── rhds/            # downstream / rhoai-2.25 lockfiles (public UBI + CentOS Stream)
│   ├── rpms.in.yaml           # references ../repos/*.repo (no subscription on 2.25)
│   ├── rpms.lock.yaml
│   ├── artifacts.in.yaml
│   └── artifacts.lock.yaml
├── code-server/     # git submodule (shared)
└── patches/         # patch files (shared)
```

After running, dependencies are in:

```
cachi2/output/deps/
├── generic/    # GPG keys, VS Code .vsix extensions
├── rpm/        # RPM packages + repodata/ (includes openshift-clients)
├── npm/        # npm tarballs
└── pip/        # Python wheels (public PyPI + RH ppc64le/s390x overlays)
```

> **Tip:** You only need to re-run this when inputs change (e.g. after editing
> `pyproject.toml`, `rpms.in.yaml`, or `artifacts.in.yaml`). The downloaded
> files in `cachi2/` can be reused across builds.

Options:

```bash
# Custom flavor (only when Dockerfile.konflux.<flavor> exists):
RELEASE_PYTHON_VERSION=3.12 BUILD_ARCH=linux/arm64 \
  ./scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds --flavor cuda
```

**Apple Silicon:** use `BUILD_ARCH=linux/arm64` for both prefetch and `gmake` (native
Podman). Default `linux/amd64` on Mac uses QEMU and may fail during `uv pip install`.

Verify prefetch before building (example checks):

```bash
ls cachi2/output/deps/pip/aiohttp_cors*   # skipped when RELEASE_PYTHON_VERSION is wrong
ls cachi2/output/deps/rpm/aarch64/repos.d/
```

### Step 3 — Build the image

The Makefile auto-detects `cachi2/output/` and adds the volume mount
automatically:

```bash
# On macOS, use gmake (GNU Make 4.0+)
gmake codeserver-ubi9-python-3.12 \
    BUILD_ARCH=linux/arm64 \
    PUSH_IMAGES=no
```

| Variable | Default | Description |
|---|---|---|
| `BUILD_ARCH` | `linux/amd64` | Target platform (`linux/amd64`, `linux/arm64`, etc.) — must match prefetch |
| `RELEASE_PYTHON_VERSION` | `3.12` | Image Python (Makefile target name); set when **prefetching** for pip markers |
| `PUSH_IMAGES` | `yes` | Set to `no` to skip pushing to registry |
| `CONTAINER_BUILD_CACHE_ARGS` | `--no-cache` | Pass `""` to enable layer caching |

The Makefile evaluates each target independently: if the target directory has
a `prefetch-input/` subdirectory AND `cachi2/output/` exists, it injects
`--volume .../cachi2/output:/cachi2/output:Z`. Other (non-hermetic) image
targets are completely unaffected.

### Alternative: manual podman build

If you prefer to run `podman build` directly instead of `make`:

```bash
podman build \
    -f codeserver/ubi9-python-3.12/Dockerfile.konflux.cpu \
    --platform linux/arm64 \
    -t codeserver-test \
    --build-arg BASE_IMAGE=registry.access.redhat.com/ubi9/python-312:latest \
    --build-arg PYLOCK_FLAVOR=cpu \
    -v "$(realpath ./cachi2/output)":/cachi2/output:z \
    -v "$(realpath ./cachi2/output/deps/rpm/aarch64/repos.d)":/etc/yum.repos.d/:z \
    .
```

#### Build arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `BASE_IMAGE` | Yes | Base image (`registry.access.redhat.com/ubi9/python-312:latest` on rhoai-2.25) |
| `PYLOCK_FLAVOR` | No (default `cpu`) | Selects `uv.lock.d/pylock.<flavor>.toml` and `requirements.<flavor>.txt` |
| `GHA_BUILD` | No | Set to `true` for GitHub Actions 16GB runner workarounds (see `build-args/cpu.conf`) |

---

## Building on GitHub Actions

The CI workflow (`.github/workflows/build-notebooks-TEMPLATE.yaml`) handles
hermetic codeserver builds:

1. **Git LFS** checkout for `.vsix` files in `utils/`.
2. **Swap** (16GB) for codeserver targets.
3. **Prefetch** — derives `COMPONENT_DIR` from the Makefile target, runs
   `prefetch-all.sh --rhds` for `product=rhoai` **without** subscription secrets.
4. **Build** — `gmake codeserver-…` with `GHA_BUILD=true`, `--layers=false`, and
   auto-mounted `cachi2/output/`.

Non-codeserver targets skip prefetch entirely.

### GHA-specific build behaviour

When `GHA_BUILD=true` (from `build-args/cpu.conf`):

- `apply-patch.sh` runs `tweak-gha.sh` (lower VS Code heap, `build_from_source=false`).
- `postinstall.sh` uses `--ignore-scripts` and selectively rebuilds native modules.
- After `release:standalone`, `copy-gha-native-bindings.sh` copies `.node` bindings
  the rsync step would otherwise drop.

See [prefetch-input/patches/README.md](prefetch-input/patches/README.md).

### ARM64 note

On arm64 GHA runners, `prefetch-all.sh` skips lockfile regeneration for RPMs
(which requires an x86_64 container) and downloads directly from the committed
`rpms.lock.yaml` using Hermeto. This avoids needing QEMU for cross-architecture
container builds.

---

## Building on Konflux

In the downstream Konflux environment, hermetic builds use a different
mechanism:

1. The Tekton PipelineRun (`.tekton/odh-workbench-codeserver-*-pull-request.yaml` and `-push.yaml`)
   defines `prefetch-input` entries that tell [cachi2](https://github.com/containerbuildsystem/cachi2)
   which lockfiles to process.
2. The `prefetch-dependencies` Tekton task runs before the build, downloading
   all dependencies into `/cachi2/output/deps/`.
3. The build uses `Dockerfile.konflux.cpu`, which is tailored for hermetic
   Konflux and local prefetch builds.
4. Konflux injects cachi2 repos automatically and manages network isolation
   at the pipeline level.
5. **Resource limits:** The codeserver PipelineRuns set `taskRunSpecs` for the
   `build-images` task (8 CPU, 32Gi memory) so the post-build rsync step
   (which transfers the large image from the remote builder) does not OOM or
   drop the connection. See [docs/konflux.md](../../docs/konflux.md).

Developers do not need to run `prefetch-all.sh` for Konflux builds — the
pipeline handles everything. The lockfiles (`rpms.lock.yaml`,
`artifacts.lock.yaml`, `requirements.cpu.txt`, `package-lock.json`) must be
committed and up-to-date.

### Tekton prefetch-input structure

```yaml
# .tekton/odh-workbench-codeserver-...-pull-request.yaml (abbreviated)
- name: prefetch-input
  value:
  - path: codeserver/ubi9-python-3.12/prefetch-input/rhds
    type: rpm
  - path: codeserver/ubi9-python-3.12/prefetch-input/rhds
    type: generic
  - path: codeserver/ubi9-python-3.12
    type: pip
    requirements_files: ["requirements.cpu.txt"]
  - path: codeserver/ubi9-python-3.12/prefetch-input/code-server/lib/vscode/extensions
    type: npm
  # ... more npm entries ...
```

---

## Why the `cachi2` volume mount?

The `-v $(realpath ./cachi2):/cachi2:z` flag (added automatically by the
Makefile, or manually for direct `podman build`) is the key to making hermetic
builds work locally.

**In production (Konflux/Tekton):** The CI pipeline runs a `prefetch-dependencies`
task before the build. This task uses [cachi2](https://github.com/containerbuildsystem/cachi2)
to download every dependency listed in the lockfiles and injects them into the
build environment at `/cachi2/output/deps/`. The build steps never touch the
network — all `dnf install`, `npm ci --offline`, and `uv pip install --no-index`
commands read exclusively from that directory.

**Locally:** There is no Konflux pipeline, so you simulate the same setup by
volume-mounting the `./cachi2` directory (populated by `prefetch-all.sh`) into
the container at `/cachi2`. This gives the Dockerfile the same
`/cachi2/output/deps/` tree it expects:

| Path inside container | Contents |
|-----------------------|----------|
| `/cachi2/output/deps/rpm/` | All RPM packages plus `repodata/` metadata. The Dockerfile points dnf at this directory as a local repo |
| `/cachi2/output/deps/pip/` | Python wheels prefetched for hermetic install (`uv pip install --no-index --find-links /cachi2/output/deps/pip`) |
| `/cachi2/output/deps/npm/` | npm tarballs. `package-lock.json` resolved URLs are rewritten to `file:///cachi2/output/deps/npm/` so `npm ci --offline` finds them |
| `/cachi2/output/deps/generic/` | GPG keys, VS Code `.vsix` from `utils/` and artifact lock |

The `:z` suffix is a SELinux relabel flag for podman — it allows the container
process to read the bind-mounted directory on SELinux-enabled hosts (Fedora,
RHEL). On macOS or systems without SELinux you can omit it.

## How repo injection works

Repos are injected by the **infrastructure**, not by the Dockerfile:

- **Local/GHA**: The Makefile volume-mounts `cachi2/output/deps/rpm/{arch}/repos.d/`
  at `/etc/yum.repos.d/`, overlaying the base image's default repos.
- **Konflux**: The `buildah-oci-ta` task volume-mounts `YUM_REPOS_D_FETCHED`
  at `/etc/yum.repos.d/` in the same way.

Both environments replace the base image's default repos with hermeto-generated
repos. These repos include module metadata (`modules.yaml`) because
`rpms.in.yaml` declares `moduleEnable: [nodejs:22]`. The Dockerfile then runs
`dnf module enable nodejs:22 -y` in each stage that installs nodejs packages.

---

## Running the image locally

After building (e.g. `make codeserver-ubi9-python-3.12` or `podman build ...`), run the
image with Podman and open code-server in your browser:

```bash
podman run -d --name codeserver -p 8080:8080 <your-image-name>:latest
```

Then open **http://localhost:8080**. The container serves the UI via nginx on port 8080
(proxying to code-server on 8787).

To bind a local directory as the workspace (e.g. for development):

```bash
podman run -d --name codeserver \
  -p 8080:8080 \
  -v /path/to/your/workspace:/opt/app-root/src:Z \
  <your-image-name>:latest
```

Use `:Z` on Fedora/RHEL for SELinux; omit on macOS. Stop with `podman stop codeserver`
and remove with `podman rm codeserver`.

---

## Runtime and container tests

- **PYTHONPATH:** The image sets `ENV PYTHONPATH=/opt/app-root/lib/python3.12/site-packages` so runtime-installed packages are found by the app Python.
- **Image metadata in CI:** On GitHub Actions, container tests run against rootful Podman. Image labels can be returned in `ContainerConfig` instead of `Config`; the test suite reads from both. See [tests/containers/docs/github-vs-local-image-metadata.md](../../tests/containers/docs/github-vs-local-image-metadata.md).
- **Startup test:** [`test/test_startup.py`](test/test_startup.py) — see [`test/README.md`](test/README.md) for Konflux/nginx logging notes.
