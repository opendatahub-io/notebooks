# Hermetic Builds

This guide explains the hermetic (offline, reproducible) build system introduced
for notebook images, starting with `codeserver/ubi9-python-3.12`.

## What is a hermetic build?

A hermetic build is a container image build that runs **without network access**.
Every dependency RPMs, npm packages, Python wheels, tarballs is downloaded
and cached before the build starts. The Dockerfile installs exclusively from
that local cache.

Benefits:

- **Reproducibility**  identical inputs produce identical outputs regardless
  of mirror availability or upstream version drift.
- **Auditability**  every package is pinned by URL + SHA-256 checksum in
  committed lockfiles, making it trivial to verify what went into an image.
- **Compliance**  required by Konflux / RHOAI release pipelines, which enforce
  network isolation during builds.

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     Lockfile inputs (committed)                  │
│                                                                  │
│  prefetch-input/odh/                                             │
│    rpms.in.yaml ─────────► rpms.lock.yaml                        │
│    artifacts.in.yaml ────► artifacts.lock.yaml                   │
│                                                                  │
│  pyproject.toml ─────────► requirements.cpu.txt                  │
│                            uv.lock.d/pylock.cpu.toml             │
│                                                                  │
│  code-server/              (git submodule)                       │
│    package-lock.json ────► npm tarballs (many)                   │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│               Prefetch  (before podman build)                    │
│                                                                  │
│  Local/GHA:   prefetch-all.sh → cachi2/output/deps/             │
│  Konflux:     prefetch-dependencies Tekton task                  │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│               Container build  (network-isolated)                │
│                                                                  │
│  podman build ... -v ./cachi2:/cachi2:z                          │
│                                                                  │
│  Dockerfile.cpu:                                                 │
│    dnf install … (from /cachi2/output/deps/rpm/)                 │
│    npm ci --offline (from /cachi2/output/deps/npm/)              │
│    uv pip install --no-index (from /cachi2/output/deps/pip/)     │
│    COPY generic artifacts (from /cachi2/output/deps/generic/)    │
└──────────────────────────────────────────────────────────────────┘
```

## Build environments

The same `Dockerfile.cpu` works across three environments. The difference is
how dependencies are prefetched and how resource limits are applied.

| Environment | Prefetch method | Resource limits | Docs |
|---|---|---|---|
| **Local** (laptop) | `prefetch-all.sh` | None (full machine resources) | [codeserver README](../codeserver/ubi9-python-3.12/README.md) |
| **GitHub Actions** | Automatic workflow step | `NODE_OPTIONS` + `JOBS` capped via `--env` | [GHA workflow](#github-actions) |
| **Konflux** | Tekton `prefetch-dependencies` task | None (large VMs) | [Konflux pipelines](#konflux) |

### Local

```bash
# 1. Init submodules
git submodule update --init --recursive

# 2. Prefetch
scripts/lockfile-generators/prefetch-all.sh \
    --component-dir codeserver/ubi9-python-3.12

# 3. Build (Makefile auto-detects cachi2/output/)
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/arm64 PUSH_IMAGES=no
```

The Makefile detects `cachi2/output/` and the target's `prefetch-input/`
directory, then injects `--volume .../cachi2/output:/cachi2/output:Z` and
`--build-arg LOCAL_BUILD=true` automatically. Non-hermetic targets are
unaffected.

See the full [codeserver README](../codeserver/ubi9-python-3.12/README.md) for
prerequisites, build arguments, and manual `podman build` instructions.

### GitHub Actions

The workflow template (`.github/workflows/build-notebooks-TEMPLATE.yaml`)
handles hermetic builds transparently for codeserver targets:

1. **Prefetch step**  gated by `contains(inputs.target, 'codeserver')`.
   Installs `pyyaml` and `uv`, then runs `prefetch-all.sh`. The prefetched
   data (~4 GB) is moved to the LVM volume and symlinked back to avoid
   filling the root partition.
2. **Build step**  runs `make` as usual. The Makefile auto-detects
   `cachi2/output/` and mounts it.
3. **Resource limits**  GHA runners have 4 vCPUs and 16 GB RAM, which is
   tight for compiling VS Code from source. The workflow injects
   `--build-arg=NODE_OPTIONS=--max-old-space-size=1024`,
   `--build-arg=JOBS=2`, and `--build-arg=MAX_OLD_SPACE_SIZE=3072` via
   `CONTAINER_BUILD_CACHE_ARGS` for codeserver targets only.
   `MAX_OLD_SPACE_SIZE` caps the main gulp process (3072 MB); transpiler
   worker threads get a fixed 2048 MB each (2 workers = 4096 MB).
   Total V8 heap budget: ~7 GB, leaving ~9 GB for OS/podman/npm.
   `NODE_OPTIONS` is unset for the memory-intensive `build:vscode` step
   so the lower limit doesn't constrain npm or child processes.
4. **Disk optimization**  `--layers=false` is passed to `podman build`
   for codeserver targets to avoid persisting intermediate layers, cutting
   peak disk usage roughly in half.

Non-codeserver targets skip all of the above.

### Konflux

In the Konflux environment, hermetic builds use the Tekton pipeline:

1. The PipelineRun YAML (`.tekton/odh-workbench-codeserver-*-pull-request.yaml`)
   declares `prefetch-input` entries pointing to lockfiles under
   `prefetch-input/odh/` (or `rhds/` for downstream).
2. The `prefetch-dependencies` Tekton task runs cachi2 to download all
   dependencies before the build.
3. `LOCAL_BUILD` is **not set** (defaults to `false`). Konflux injects repos
   automatically and manages network isolation at the pipeline level.
4. No `NODE_OPTIONS` or `JOBS` limits  Konflux VMs have significantly
   more resources than GHA runners.

Developers do not run `prefetch-all.sh` for Konflux  the pipeline handles
everything. The lockfiles must be committed and up-to-date.

## What changed to make builds hermetic

### Dockerfile.cpu (multi-stage, network-isolated)

The Dockerfile was rewritten from a network-dependent build to a fully offline
one. Key changes in each stage:

**`rpm-base` stage**  builds code-server from prefetched source:
- `code-server` source is vendored as a git submodule under
  `prefetch-input/code-server/` instead of being `git clone`'d at build time.
- Node.js is installed from prefetched RPMs (via `dnf install nodejs` from
  the local cachi2 repo) instead of downloading via nvm.
- `npm ci --offline` replaces `npm install`: all `resolved` URLs in
  `package-lock.json` are rewritten to `file:///cachi2/output/deps/npm/`.
- Electron, node-gyp headers, Playwright, ripgrep, and VS Code extensions
  are copied from prefetched generic artifacts instead of being downloaded.
- `nfpm` (RPM packager) is installed from a prefetched RPM instead of
  downloading from GitHub.

**`whl-cache` stage**  new stage for Python wheel compilation:
- On `ppc64le` / `s390x`, some Python packages lack pre-built wheels.
  This stage installs them from prefetched wheels and exports the compiled
  `.whl` files for reuse by the final stage.

**`cpu-base` stage**  OS packages and tools:
- All `dnf install` commands use the local cachi2 RPM repo when
  `LOCAL_BUILD=true`.
- The `oc` client is installed from a prefetched tarball instead of
  downloading from mirror.openshift.com.

**`codeserver` stage**  final image:
- Python packages are installed with `uv pip install --no-index --find-links
  /cachi2/output/deps/pip/`.
- The code-server RPM is copied from the `rpm-base` stage.

### Lockfiles and inputs (prefetch-input/)

New files committed under `codeserver/ubi9-python-3.12/prefetch-input/`:

| File | Purpose |
|------|---------|
| `odh/rpms.in.yaml` | RPM package list + repo definitions (upstream) |
| `odh/rpms.lock.yaml` | Resolved RPM URLs + checksums per arch |
| `odh/artifacts.in.yaml` | Generic artifact URLs (GPG keys, tarballs, etc.) |
| `odh/artifacts.lock.yaml` | Resolved URLs + SHA-256 checksums |
| `rhds/rpms.in.yaml` | RPM package list (downstream, RHEL repos) |
| `rhds/artifacts.in.yaml` | Generic artifacts (downstream) |
| `repos/` | Shared DNF `.repo` files (ubi, centos, epel) |
| `patches/` | Build patches for offline operation |
| `code-server/` | Git submodule (vendored source) |

### Lockfile generators (scripts/lockfile-generators/)

A suite of scripts to generate, resolve, and download hermetic build
dependencies. See the full
[lockfile-generators README](../scripts/lockfile-generators/README.md) for
detailed usage.

| Script | Purpose |
|--------|---------|
| `prefetch-all.sh` | Orchestrator  runs all four generators in order |
| `create-artifact-lockfile.py` | Generic artifacts → `artifacts.lock.yaml` |
| `create-rpm-lockfile.sh` | RPMs → `rpms.lock.yaml` (via `rpm-lockfile-prototype`) |
| `download-npm.sh` | npm tarballs → `cachi2/output/deps/npm/` |
| `create-requirements-lockfile.sh` | pip → `pylock.toml` + `requirements.txt` |

### Makefile

The `build_image` macro was updated to auto-detect hermetic builds:

```makefile
$(eval CACHI2_VOLUME := $(if $(and $(wildcard cachi2/output),$(wildcard $(BUILD_DIR)prefetch-input)), \
    --volume $(ROOT_DIR)cachi2/output:/cachi2/output:Z --build-arg LOCAL_BUILD=true,))
```

This evaluates per-target: only targets with both `cachi2/output/` and a
`prefetch-input/` directory get the volume mount and `LOCAL_BUILD=true`.
All other targets are completely unaffected.

### GitHub Actions workflow

Changes to `.github/workflows/build-notebooks-TEMPLATE.yaml`:

- **Prefetch step** added before the build for codeserver targets.
- **Submodule checkout** (`submodules: recursive`) enabled for codeserver.
- **Disk management**  codeserver is included in the "free up disk space"
  step; prefetched data is moved to the LVM volume.
- **Resource limits**  `--build-arg=NODE_OPTIONS=--max-old-space-size=1024`,
  `--build-arg=JOBS=2`, and `--build-arg=MAX_OLD_SPACE_SIZE=3072` injected
  for codeserver via `CONTAINER_BUILD_CACHE_ARGS`.
- **Layer optimization**  `--layers=false` for codeserver builds.

### Tekton pipelines (.tekton/)

Updated PipelineRun YAMLs to:
- Set `hermetic: "true"`.
- Add `prefetch-input` entries pointing to `prefetch-input/odh/` for RPMs
  and generic artifacts, and to every `package-lock.json` directory for npm.
- Reference `multiarch-combined-pipeline` with `enable-cache-proxy: "true"`.

### sandbox.py

Updated to handle:
- Git submodule directories in the build context.
- macOS `PermissionError` with dotfiles/xattrs during context copying.
- Glob pattern expansion for prerequisites.

## Upstream (ODH) vs downstream (RHDS)

Lockfiles are organized into two variant directories:

```
prefetch-input/
├── repos/           # shared .repo files
├── odh/             # upstream (UBI + CentOS Stream + EPEL repos)
│   ├── rpms.in.yaml
│   ├── rpms.lock.yaml
│   ├── artifacts.in.yaml
│   └── artifacts.lock.yaml
└── rhds/            # downstream (RHEL subscription repos)
    ├── rpms.in.yaml
    └── artifacts.in.yaml
```

The `--rhds` flag on `prefetch-all.sh` switches to the downstream variant:

```bash
# Upstream (default)
scripts/lockfile-generators/prefetch-all.sh --component-dir codeserver/ubi9-python-3.12

# Downstream
scripts/lockfile-generators/prefetch-all.sh --component-dir codeserver/ubi9-python-3.12 \
    --rhds --activation-key my-key --org my-org
```

Tekton PipelineRun YAMLs point at `prefetch-input/odh` for upstream or
`prefetch-input/rhds` for downstream.

## LOCAL_BUILD=true vs production

When `LOCAL_BUILD=true` is set (automatically by the Makefile for local and GHA
builds), the Dockerfile:

1. Removes default yum repos (`rm -f /etc/yum.repos.d/*`).
2. Copies hermeto-generated `.repo` files from the cachi2 RPM directory so
   `dnf` resolves packages from prefetched RPMs only.
3. Disables the `nodejs` module stream (hermeto repos provide nodejs directly).

When `LOCAL_BUILD` is unset or `false` (Konflux), the Dockerfile:

1. Keeps the default repos (Konflux injects cachi2 repos automatically).
2. Enables `nodejs:22` module stream via `dnf module enable nodejs:22 -y`.

## Further reading

- [codeserver/ubi9-python-3.12/README.md](../codeserver/ubi9-python-3.12/README.md) —
  build instructions for the codeserver image (local, GHA, Konflux).
- [scripts/lockfile-generators/README.md](../scripts/lockfile-generators/README.md) —
  detailed documentation for all lockfile generator scripts.
- [docs/konflux.md](konflux.md)  Konflux environment links and tenant setup.
