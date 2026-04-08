# Hermetic Build Architecture for Codeserver

## Overview

The codeserver workbench (`codeserver/ubi9-python-3.12`) uses a fully hermetic build
where all dependencies (RPMs, npm packages, Python wheels, generic tarballs) are
prefetched before the Docker build runs. The build operates without network access.

## Build Chain

```
prefetch-all.sh → populates cachi2/output/deps/
Makefile         → detects cachi2/output/ → injects --volume into podman build
sandbox.py       → creates minimal build context from Dockerfile COPY/ADD directives
podman build     → runs Dockerfile with /cachi2/output/ mounted
```

### prefetch-all.sh

Orchestrates four lockfile generators in sequence:

| Step | Generator | Input | Output |
|------|-----------|-------|--------|
| 1 | `create-artifact-lockfile.py` | `artifacts.in.yaml` | `cachi2/output/deps/generic/` (GPG keys, nfpm, node headers, oc client, VS Code extensions) |
| 2 | `create-requirements-lockfile.sh` | `pyproject.toml` | `cachi2/output/deps/pip/` (Python wheels) |
| 3 | `download-npm.sh` | `package-lock.json` files | `cachi2/output/deps/npm/` (npm tarballs) |
| 4 | `hermeto-fetch-rpm.sh` | `rpms.lock.yaml` | `cachi2/output/deps/rpm/{arch}/` (RPMs + repo metadata) |

Variants are selected via `--rhds` flag:
- Default (`odh`): uses CentOS Stream + UBI repos (no subscription needed)
- `--rhds`: uses RHEL subscription repos (needs `--activation-key` and `--org`)

### Makefile auto-detection

```makefile
$(eval CACHI2_VOLUME := $(if $(and $(wildcard cachi2/output),$(wildcard $(BUILD_DIR)prefetch-input)),\
    --volume $(ROOT_DIR)cachi2/output:/cachi2/output:Z \
    --volume $(ROOT_DIR)cachi2/output/deps/rpm/$(RPM_ARCH)/repos.d/:/etc/yum.repos.d/:Z,))
```

When both `cachi2/output/` and `<target>/prefetch-input/` exist, the Makefile
automatically mounts the prefetched dependencies into the build. The second
mount overlays `/etc/yum.repos.d/` with hermeto-generated repos, making local
builds behave like Konflux (repos are already in place when the Dockerfile runs).

### sandbox.py

Wraps `podman build` by creating a minimal build context:
1. Parses the Dockerfile using `bin/buildinputs` (Go tool, Dockerfile → LLB → JSON)
2. Identifies all files referenced in COPY/ADD directives
3. Creates a temporary directory with only those files
4. Passes `{}` placeholder to podman which gets replaced with the tmpdir path

sandbox.py does NOT modify volumes, build args, or repos — it only manages the
build context.

## cachi2/output Directory Structure

After prefetching, the directory looks like:

```
cachi2/output/
├── deps/
│   ├── rpm/
│   │   ├── x86_64/
│   │   │   ├── <repo-name>/       # RPM files + repodata/
│   │   │   └── repos.d/           # Generated .repo files with file:// URLs
│   │   ├── aarch64/
│   │   ├── ppc64le/
│   │   └── s390x/
│   ├── npm/                       # npm tarballs
│   ├── pip/                       # Python wheels
│   └── generic/                   # GPG keys, tarballs, etc.
├── bom.json
└── .build-config.json
```

Key detail: hermeto generates `.repo` files in `repos.d/` but does **not** include
`module_hotfixes=1`. Our `hermeto-fetch-rpm.sh` wrapper injects it
(`perl -pi -e '$_ .= "module_hotfixes=1\n" if /^\[/' ...`) on lines 132-137.
Konflux's `prefetch-dependencies-oci-ta` Tekton task runs cachi2/hermeto directly
(not our wrapper), so **Konflux repos do NOT have `module_hotfixes=1`**.

`module_hotfixes=1` is needed because `rpms.in.yaml` resolves packages from the
`nodejs:22` module stream (`moduleEnable: [nodejs:22]`), but hermeto's generated
repos don't carry module metadata. Without `module_hotfixes=1`, DNF's modular
filtering blocks these packages (e.g. `nodejs-devel`).

## Three Build Environments

### Local development

```bash
scripts/lockfile-generators/prefetch-all.sh --component-dir codeserver/ubi9-python-3.12
make codeserver-ubi9-python-3.12
```

Makefile detects `cachi2/output/` and auto-injects the volume mount.

### GitHub Actions

The TEMPLATE workflow (`build-notebooks-TEMPLATE.yaml`) handles it transparently:

1. **Prefetch step**: runs `prefetch-all.sh`, outputs `EXTRA_BUILD_ARGS` with
   volume mount
2. **Build step**: runs `make` with `CONTAINER_BUILD_CACHE_ARGS` containing
   the volume mount
3. For subscription builds (AIPCC), passes `--rhds --activation-key ... --org ...`
   to use the RHDS variant lockfiles

### Konflux (Tekton)

1. PipelineRun YAML declares `prefetch-input` entries pointing to lockfiles
2. cachi2's `prefetch-dependencies` task downloads everything using hermeto
3. Build task mounts `/cachi2/output/` automatically
4. Network isolation enforced at the pipeline level

All three environments produce the same `/cachi2/output/deps/` structure because
they all use hermeto under the hood for RPM prefetching.

## Variant Directories (ODH vs RHDS)

Lockfiles are organized into two variant directories under `prefetch-input/`:

```
prefetch-input/
├── odh/             # upstream (CentOS Stream + UBI repos)
│   ├── rpms.in.yaml
│   ├── rpms.lock.yaml
│   ├── artifacts.in.yaml
│   └── artifacts.lock.yaml
├── rhds/            # downstream (RHEL subscription repos)
│   ├── rpms.in.yaml
│   ├── rpms.lock.yaml
│   ├── artifacts.in.yaml
│   └── artifacts.lock.yaml
├── repos/           # shared DNF repo definitions
├── code-server/     # git submodule (vendored source)
└── patches/         # build patches for offline operation
```

ODH uses CentOS Stream packages; RHDS uses RHEL packages. The choice matters
because base images differ: ODH uses a c9s base, AIPCC uses a RHEL base.
Mixing variants causes RPM conflicts (see openssl-fips-provider-conflict.md).

## Dockerfile Structure

The Dockerfile is multi-stage with 5 stages:

| Stage | Purpose |
|-------|---------|
| `rpm-base` | Builds code-server from source into an RPM |
| `whl-cache` | Installs Python wheels, exports compiled C-extension wheels for ppc64le/s390x |
| `cpu-base` | Installs OS packages + tools (oc client, micropipenv, uv) |
| `codeserver` | Final image (code-server + nginx + Python packages) |
| `tests` | Smoke test stage |

Each stage that runs `dnf install` needs repos configured. Repos are injected
by the infrastructure, not by the Dockerfile:

- **Local/GHA**: The Makefile volume-mounts `repos.d/` at `/etc/yum.repos.d/`,
  overlaying the base image's default repos. These repos already have
  `module_hotfixes=1` (added by `hermeto-fetch-rpm.sh`).
- **Konflux**: The `prefetch-dependencies` buildah task injects cachi2 repos
  into `/etc/yum.repos.d/` (repos lack `module_hotfixes=1`).

The Dockerfile runs an idempotent `sed` to ensure `module_hotfixes=1` is present:

```dockerfile
RUN sed -i '/^\[/a module_hotfixes=1' /etc/yum.repos.d/*.repo
```

This is a no-op in Local/GHA (already present) and adds it in Konflux (where
it's missing). No `LOCAL_BUILD` build arg, no if/else branching, no `rm -f`
or `cp` of repos.

## `module_hotfixes=1` — wrapper-only injection

Hermeto itself does **not** add `module_hotfixes=1` to generated repos. Our
`hermeto-fetch-rpm.sh` wrapper (line 132-137) injects it after hermeto runs:

```bash
find "$HERMETO_STAGING/deps/rpm" -name '*.repo' -exec \
  perl -pi -e '$_ .= "module_hotfixes=1\n" if /^\[/' {} +
```

This means:
- **Local/GHA** (uses our wrapper): repos **have** `module_hotfixes=1`
- **Konflux** (uses `prefetch-dependencies-oci-ta` task directly): repos
  **do not have** `module_hotfixes=1`

This asymmetry was the original reason for the `LOCAL_BUILD` branching:
`dnf module disable nodejs` (Local/GHA, module_hotfixes handles it) vs
`dnf module enable nodejs:22` (Konflux, no module_hotfixes, explicit enable
needed). The fix is:

1. The Makefile now volume-mounts `repos.d/` at `/etc/yum.repos.d/` (so the
   Dockerfile never needs to `rm -f` + `cp` repos).
2. The Dockerfile runs `sed -i '/^\[/a module_hotfixes=1'` which is idempotent
   — no-op in Local/GHA (already present), adds it in Konflux (missing).

This eliminates all `LOCAL_BUILD` branching and `dnf module enable/disable`.
