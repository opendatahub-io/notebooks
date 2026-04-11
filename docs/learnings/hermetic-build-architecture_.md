# Hermetic Build Architecture for Codeserver

## Overview

The codeserver workbench (`codeserver/ubi9-python-3.12`) uses a fully hermetic build
where all dependencies (RPMs, npm packages, Python wheels, generic tarballs) are
prefetched before the Docker build runs. The build operates without network access.

## Build Chain

```text
prefetch-all.sh → populates cachi2/output/<hash>/deps/
Makefile         → detects cachi2/output/ → injects --volume into podman build
sandbox.py       → creates minimal build context from Dockerfile COPY/ADD directives
podman build     → runs Dockerfile with /cachi2/output/ mounted
```

### prefetch-all.sh

Orchestrates five lockfile generators in sequence:

| Step | Generator | Input | Output |
|------|-----------|-------|--------|
| 1 | `create-artifact-lockfile.py` | `artifacts.in.yaml` | `cachi2/output/<hash>/deps/generic/` (GPG keys, nfpm, node headers, oc client, VS Code extensions) |
| 2 | `create-requirements-lockfile.sh` | `pyproject.toml` | `cachi2/output/<hash>/deps/pip/` (Python wheels) |
| 3 | `download-npm.sh` | `package-lock.json` files | `cachi2/output/<hash>/deps/npm/` (npm tarballs) |
| 4 | `hermeto-fetch-rpm.sh` | `rpms.lock.yaml` | `cachi2/output/<hash>/deps/rpm/{arch}/` (RPMs + repo metadata) |
| 5 | `create-go-lockfile.sh` | `go.mod` (via git submodule) | `cachi2/output/<hash>/deps/gomod/` (Go modules) |

Variants are selected via `--rhds` flag:
- Default (`odh`): uses CentOS Stream + UBI repos (no subscription needed)
- `--rhds`: uses RHEL subscription repos (needs `--activation-key` and `--org`)

### Makefile auto-detection

```makefile
$(eval COMPONENT_DIR_STR := $(patsubst %/,%,$(BUILD_DIR)))
$(eval CACHI2_HASH := $(shell python3 -c "import hashlib; print(hashlib.md5('$(COMPONENT_DIR_STR)'.encode()).hexdigest())"))
$(eval CACHI2_DIR := cachi2/output/$(CACHI2_HASH))
$(eval CACHI2_VOLUME := $(if $(and $(wildcard $(CACHI2_DIR)),$(wildcard $(BUILD_DIR)prefetch-input)),\
    --volume $(ROOT_DIR)$(CACHI2_DIR):/cachi2/output:Z \
    --volume $(ROOT_DIR)$(CACHI2_DIR)/deps/rpm/$(RPM_ARCH)/repos.d/:/etc/yum.repos.d/:Z,))
```

When both `cachi2/output/<hash>/` and `<target>/prefetch-input/` exist, the Makefile
automatically mounts the per-component prefetched dependencies into the build.
The `<hash>` is the MD5 of the component directory name, allowing concurrent
builds of different components without collisions. The second mount overlays
`/etc/yum.repos.d/` with hermeto-generated repos, making local builds behave
like Konflux (repos are already in place when the Dockerfile runs).

### sandbox.py

Wraps `podman build` by creating a minimal build context:
1. Parses the Dockerfile using `bin/buildinputs` (Go tool, Dockerfile → LLB → JSON)
2. Identifies all files referenced in COPY/ADD directives
3. Creates a temporary directory with only those files
4. Passes `{}` placeholder to podman which gets replaced with the tmpdir path

sandbox.py does NOT modify volumes, build args, or repos — it only manages the
build context.

## cachi2/output Directory Structure

After prefetching, each component gets its own namespaced directory under
`cachi2/output/<hash>/` (where `<hash>` is the MD5 of the component directory
name, e.g. `cachi2/output/a1b2c3.../`). This prevents collisions when building
multiple components in parallel.

```text
cachi2/output/
└── <hash>/                        # per-component namespace (MD5 of component dir)
    ├── deps/
    │   ├── rpm/
    │   │   ├── x86_64/
    │   │   │   ├── <repo-name>/   # RPM files + repodata/
    │   │   │   └── repos.d/       # Generated .repo files with file:// URLs
    │   │   ├── aarch64/
    │   │   ├── ppc64le/
    │   │   └── s390x/
    │   ├── npm/                   # npm tarballs
    │   ├── pip/                   # Python wheels
    │   └── generic/               # GPG keys, tarballs, etc.
    ├── bom.json
    └── .build-config.json
```

The Makefile mounts `cachi2/output/<hash>/` at `/cachi2/output/` inside the
container, so the Dockerfile always sees `/cachi2/output/deps/...` regardless
of which component is being built.

Key detail: when `rpms.in.yaml` declares `moduleEnable: [nodejs:22]`, hermeto
downloads module metadata (`modules.yaml`) alongside the RPMs and includes it
in the generated repodata. This allows `dnf module enable nodejs:22` to work
with the hermeto repos. Both our `hermeto-fetch-rpm.sh` wrapper and Konflux's
`prefetch-dependencies-oci-ta` task produce repos with this metadata.

## Three Build Environments

### Local development

```bash
scripts/lockfile-generators/prefetch-all.sh --component-dir codeserver/ubi9-python-3.12
make codeserver-ubi9-python-3.12
```

Makefile detects `cachi2/output/<hash>/` and auto-injects the volume mount.

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
3. Build task mounts deps at `/cachi2/output/` automatically
4. Network isolation enforced at the pipeline level

All three environments produce the same `/cachi2/output/deps/` layout inside
the container because they all use hermeto under the hood for RPM prefetching.
On the host, local/GHA builds use `cachi2/output/<hash>/deps/` while Konflux
uses its own staging directory.

## Variant Directories (ODH vs RHDS)

Lockfiles are organized into two variant directories under `prefetch-input/`:

```text
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
  overlaying the base image's default repos.
- **Konflux**: The `buildah-oci-ta` task volume-mounts `YUM_REPOS_D_FETCHED`
  at `/etc/yum.repos.d/` in the same way.

Both environments replace the base image's default repos. For targets that
need nodejs (codeserver), `rpms.in.yaml` declares `moduleEnable: [nodejs:22]`,
which makes hermeto include module metadata in the repodata. The Dockerfile
runs `dnf module enable nodejs:22 -y` to activate the module stream.

No `LOCAL_BUILD` build arg, no if/else branching, no `rm -f` or `cp` of repos.
