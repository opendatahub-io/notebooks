# codeserver/ubi9-python-3.12

Code-server (VS Code in the browser) image with Python 3.12 on UBI 9, built
for Open Data Hub / OpenShift AI workbenches.

## Hermetic build overview

Every dependency (RPMs, npm packages, Python wheels, generic tarballs) is
prefetched ahead of time and served from a local `cachi2/` directory. No
network access is needed during the image build itself.

There are three ways to build this image:

| Environment | Prefetch method | Build command |
|---|---|---|
| **Local (laptop)** | `prefetch-all.sh` | `make codeserver-ubi9-python-3.12` |
| **GitHub Actions** | Automatic (workflow step) | Push to PR — CI runs automatically |
| **Konflux** | Tekton `prefetch-dependencies` task | Managed by pipeline |

---

## Building locally

### Prerequisites

| Tool | Purpose |
|------|---------|
| GNU Make 4.0+ (`gmake` on macOS) | Runs the build pipeline |
| `podman` (or `docker`) | Container build engine |
| `python3` + `pyyaml` | Runs the artifact lockfile generator |
| `uv` | Resolves Python dependencies (`pip install uv`) |
| `wget`, `jq` | Downloads artifacts and npm tarballs |

### Step 1 — Initialize git submodules

The code-server source is vendored as a git submodule:

```bash
git submodule update --init --recursive
```

### Step 2 — Prefetch all dependencies

Run from the **repository root**:

```bash
# Upstream ODH (default):
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12

# Downstream RHDS:
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --rhds \
    --activation-key my-key --org my-org
```

This single command orchestrates all four lockfile generators:
1. Generic artifacts (GPG keys, node headers, nfpm, oc client, VS Code extensions)
2. Pip wheels (numpy, scipy, pandas, scikit-learn, etc. via RHOAI index)
3. NPM packages (code-server + VS Code extensions)
4. RPMs (gcc, nodejs, nginx, openblas, etc. via Hermeto)

Lockfiles are organized into variant subdirectories under `prefetch-input/`:

```
prefetch-input/
├── repos/           # shared DNF repo definitions (ubi, centos, epel, rhsm-pulp)
├── odh/             # upstream lockfiles (UBI + CentOS Stream repos)
│   ├── rpms.in.yaml           # references ../repos/*.repo
│   ├── rpms.lock.yaml
│   ├── artifacts.in.yaml
│   └── artifacts.lock.yaml
├── rhds/            # downstream lockfiles (RHEL subscription repos)
│   ├── rpms.in.yaml           # references ../repos/*.repo + /etc/yum.repos.d/redhat.repo
│   └── artifacts.in.yaml
├── code-server/     # git submodule (shared)
└── patches/         # patch files (shared)
```

After running, dependencies are in:

```
cachi2/output/deps/
├── generic/    # GPG keys, tarballs, nfpm RPM, oc client, VS Code extensions
├── rpm/        # RPM packages + repodata/
├── npm/        # npm tarballs
└── pip/        # Python wheels
```

> **Tip:** You only need to re-run this when inputs change (e.g. after editing
> `pyproject.toml`, `rpms.in.yaml`, or `artifacts.in.yaml`). The downloaded
> files in `cachi2/` can be reused across builds.

Options:

```bash
# Custom flavor (e.g. cuda):
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12 --flavor cuda
```

### Step 3 — Build the image

The Makefile auto-detects `cachi2/output/` and adds the volume mount +
`LOCAL_BUILD=true` build arg automatically:

```bash
# On macOS, use gmake (GNU Make 4.0+)
gmake codeserver-ubi9-python-3.12 \
    BUILD_ARCH=linux/arm64 \
    PUSH_IMAGES=no
```

| Variable | Default | Description |
|---|---|---|
| `BUILD_ARCH` | `linux/amd64` | Target platform (`linux/amd64`, `linux/arm64`, etc.) |
| `PUSH_IMAGES` | `yes` | Set to `no` to skip pushing to registry |
| `CONTAINER_BUILD_CACHE_ARGS` | `--no-cache` | Pass `""` to enable layer caching |

The Makefile evaluates each target independently: if the target directory has
a `prefetch-input/` subdirectory AND `cachi2/output/` exists, it injects:
- `--volume .../cachi2/output:/cachi2/output:Z`
- `--build-arg LOCAL_BUILD=true`

Other (non-hermetic) image targets are completely unaffected.

### Alternative: manual podman build

If you prefer to run `podman build` directly instead of `make`:

```bash
podman build \
    -f codeserver/ubi9-python-3.12/Dockerfile.cpu \
    --platform linux/amd64 \
    -t codeserver-test \
    --build-arg ARCH=amd64 \
    --build-arg LOCAL_BUILD=true \
    --build-arg BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest \
    --build-arg PYLOCK_FLAVOR=cpu \
    -v "$(realpath ./cachi2)":/cachi2:z \
    .
```

#### Build arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `BASE_IMAGE` | Yes | Base image to build from (e.g. `quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest`) |
| `ARCH` | Yes | Target architecture for RPM naming (`amd64`, `aarch64`, `ppc64le`, `s390x`) |
| `LOCAL_BUILD` | Yes | Set to `true` for local builds. Configures dnf to use the local cachi2 RPM repo instead of Konflux-injected repos |
| `PYLOCK_FLAVOR` | Yes | Python lockfile flavor (`cpu` or `cuda`). Selects `uv.lock.d/pylock.<flavor>.toml` |

---

## Building on GitHub Actions

The CI workflow (`.github/workflows/build-notebooks-TEMPLATE.yaml`) handles
hermetic builds automatically for codeserver targets:

1. A **"Prefetch hermetic build dependencies"** step runs before the build.
   It derives the component directory from the make target name, installs
   `pyyaml` and `uv`, and executes `prefetch-all.sh`.
2. The **"Build"** step runs `make codeserver-ubi9-python-3.12` as usual.
   The Makefile auto-detects the `cachi2/output/` directory created in step 1
   and injects the volume mount + `LOCAL_BUILD=true`.

This is transparent — no special CI configuration is needed beyond the
workflow template. Non-codeserver targets skip the prefetch step entirely.

### How it works

The prefetch step is gated by `contains(inputs.target, 'codeserver')`:

```yaml
- name: "Prefetch hermetic build dependencies"
  if: ${{ contains(inputs.target, 'codeserver') }}
  run: |
    COMPONENT_DIR=$(echo "${{ inputs.target }}" | sed 's|-|/|')
    if [ -d "$COMPONENT_DIR/prefetch-input" ]; then
      scripts/lockfile-generators/prefetch-all.sh --component-dir "$COMPONENT_DIR"
    fi
```

### ARM64 note

On arm64 GHA runners, `prefetch-all.sh` skips lockfile regeneration for RPMs
(which requires an x86_64 container) and downloads directly from the committed
`rpms.lock.yaml` using Hermeto. This avoids needing QEMU for cross-architecture
container builds.

---

## Building on Konflux

In the downstream Konflux environment, hermetic builds use a different
mechanism:

1. The Tekton PipelineRun (`.tekton/odh-workbench-codeserver-*-pull-request.yaml`)
   defines `prefetch-input` entries that tell [cachi2](https://github.com/containerbuildsystem/cachi2)
   which lockfiles to process.
2. The `prefetch-dependencies` Tekton task runs before the build, downloading
   all dependencies into `/cachi2/output/deps/`.
3. The build uses `Dockerfile.konflux.cpu` (not `Dockerfile.cpu`) which is
   tailored for the Konflux environment.
4. `LOCAL_BUILD` is **not set** — Konflux injects cachi2 repos automatically
   and manages network isolation at the pipeline level.

Developers do not need to run `prefetch-all.sh` for Konflux builds — the
pipeline handles everything. The lockfiles (`rpms.lock.yaml`,
`artifacts.lock.yaml`, `requirements.cpu.txt`, `package-lock.json`) must be
committed and up-to-date.

### Tekton prefetch-input structure

```yaml
# .tekton/odh-workbench-codeserver-...-pull-request.yaml (abbreviated)
- name: prefetch-input
  value:
  - path: codeserver/ubi9-python-3.12/prefetch-input/odh   # use 'rhds' for downstream
    type: rpm
  - path: codeserver/ubi9-python-3.12/prefetch-input/odh
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
| `/cachi2/output/deps/pip/` | Python wheels prefetched from the RHOAI index. Installed with `uv pip install --no-index --find-links /cachi2/output/deps/pip` |
| `/cachi2/output/deps/npm/` | npm tarballs. `package-lock.json` resolved URLs are rewritten to `file:///cachi2/output/deps/npm/` so `npm ci --offline` finds them |
| `/cachi2/output/deps/generic/` | Everything else: GPG keys, node-gyp headers, Electron binaries, ripgrep, nfpm RPM, the oc client tarball, VS Code extensions, etc. |

The `:z` suffix is a SELinux relabel flag for podman — it allows the container
process to read the bind-mounted directory on SELinux-enabled hosts (Fedora,
RHEL). On macOS or systems without SELinux you can omit it.

## `LOCAL_BUILD=true` vs production

When `LOCAL_BUILD=true` is set, the Dockerfile:

1. **Removes default yum repos** (`rm -f /etc/yum.repos.d/*`) so dnf does not
   attempt to reach Red Hat CDN or UBI repos.
2. **Adds the local cachi2 RPM repo** (`dnf config-manager --add-repo
   file:///cachi2/output/deps/rpm/`) so all `dnf install` commands resolve
   packages from the prefetched RPMs.

In production (Konflux), `LOCAL_BUILD` is unset (defaults to `false`). Konflux
injects cachi2 repos automatically and manages network isolation at the pipeline
level.
