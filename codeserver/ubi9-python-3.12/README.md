# codeserver/ubi9-python-3.12

Code-server (VS Code in the browser) image with Python 3.12 on UBI 9, built
for Open Data Hub / OpenShift AI workbenches.

## Building locally with podman

The Dockerfile uses a **hermetic build** model: every dependency (RPMs, npm
packages, Python wheels, generic tarballs) is prefetched ahead of time and
served from a local `cachi2/` directory. No network access is needed during the
build itself.

### Prerequisites

| Tool | Purpose |
|------|---------|
| `podman` (or `docker`) | Container build engine |
| `python3` | Runs the artifact lockfile generator |
| `uv` | Resolves Python dependencies (`pip install uv`) |
| `wget` | Downloads artifacts and wheels |

### Step 1 — Initialize git submodules

The code-server source is vendored as a git submodule. It must be checked out
before building:

```bash
git submodule update --init --recursive
```

### Step 2 — Generate lockfiles and download dependencies

All commands run from the **repository root**. The `--download` flag fetches
packages into `cachi2/output/deps/` for local use.

```bash
# 1. Generic artifacts (GPG keys, node headers, nfpm, oc client, etc.)
python3 scripts/lockfile-generators/create-artifact-lockfile.py \
    --artifact-input codeserver/ubi9-python-3.12/prefetch-input/artifacts.in.yaml \
    --download

# 2. RPM packages (gcc, nodejs, nginx, openblas, etc.)
./scripts/lockfile-generators/create-rpm-lockfile.sh \
    --rpm-input codeserver/ubi9-python-3.12/prefetch-input/rpms.in.yaml \
    --download

# 3. npm packages (code-server + VS Code extensions)
./scripts/lockfile-generators/download-npm.sh \
    --tekton-file .tekton/odh-workbench-codeserver-datascience-cpu-py312-ubi9-pull-request.yaml

# 4. Python wheels (numpy, scipy, pandas, scikit-learn, etc.) via RHOAI index
./scripts/lockfile-generators/create-requirements-lockfile.sh \
    --pyproject-toml codeserver/ubi9-python-3.12/pyproject.toml \
    --download
```

After running these, the local directory tree looks like:

```
cachi2/output/deps/
├── generic/    # GPG keys, tarballs, nfpm RPM, oc client, VS Code extensions
├── rpm/        # RPM packages + repodata/
├── npm/        # npm tarballs
└── pip/        # Python wheels
```

> **Tip:** You only need to re-run a generator when its inputs change (e.g.
> after editing `pyproject.toml`, `rpms.in.yaml`, or `artifacts.in.yaml`).
> The downloaded files in `cachi2/` can be reused across builds.

### Step 3 — Build the image

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

### Why the `cachi2` volume mount?

The `-v $(realpath ./cachi2):/cachi2:z` flag is the key to making hermetic
builds work locally.

**In production (Konflux/Tekton):** The CI pipeline runs a `prefetch-dependencies`
task before the build. This task uses [cachi2](https://github.com/containerbuildsystem/cachi2)
to download every dependency listed in the lockfiles and injects them into the
build environment at `/cachi2/output/deps/`. The build steps never touch the
network — all `dnf install`, `npm ci --offline`, and `uv pip install --no-index`
commands read exclusively from that directory.

**Locally:** There is no Konflux pipeline, so you simulate the same setup by
volume-mounting the `./cachi2` directory (populated in Step 2) into the container
at `/cachi2`. This gives the Dockerfile the same `/cachi2/output/deps/` tree it
expects:

| Path inside container | Contents |
|-----------------------|----------|
| `/cachi2/output/deps/rpm/` | All RPM packages plus `repodata/` metadata. The Dockerfile points dnf at this directory as a local repo (`dnf config-manager --add-repo file:///cachi2/output/deps/rpm/`) |
| `/cachi2/output/deps/pip/` | Python wheels prefetched from the RHOAI index. Installed with `uv pip install --no-index --find-links /cachi2/output/deps/pip` |
| `/cachi2/output/deps/npm/` | npm tarballs. `package-lock.json` resolved URLs are rewritten to `file:///cachi2/output/deps/npm/` so `npm ci --offline` finds them |
| `/cachi2/output/deps/generic/` | Everything else: GPG keys, node-gyp headers, Electron binaries, ripgrep, nfpm RPM, the oc client tarball, VS Code extensions, etc. |

Without the volume mount, every `RUN` instruction that reads from `/cachi2/...`
would fail immediately because the directory simply would not exist inside the
build container.

The `:z` suffix is a SELinux relabel flag for podman — it allows the container
process to read the bind-mounted directory on SELinux-enabled hosts (Fedora,
RHEL). On macOS or systems without SELinux you can omit it.

### `LOCAL_BUILD=true` vs production

When `LOCAL_BUILD=true` is set, the Dockerfile:

1. **Removes default yum repos** (`rm -f /etc/yum.repos.d/*`) so dnf does not
   attempt to reach Red Hat CDN or UBI repos.
2. **Adds the local cachi2 RPM repo** (`dnf config-manager --add-repo
   file:///cachi2/output/deps/rpm/`) so all `dnf install` commands resolve
   packages from the prefetched RPMs.

In production (Konflux), `LOCAL_BUILD` is unset (defaults to `false`). Konflux
injects cachi2 repos automatically and manages network isolation at the pipeline
level.
