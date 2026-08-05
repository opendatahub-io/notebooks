# codeserver-baseline/ubi9-python-3.12

Phase 1 baseline code-server workbench image with Python 3.12 on UBI 9.

## Status

- Builds `code-server` from the baseline-owned `code-server/` submodule.
- Resolves RPM, npm, and Python dependencies online during the image build.
- Installs Python packages from the checked-in root `pylock.toml` using PyPI.
- Keeps hermetic `prefetch-input/` conversion deferred to phase 2.

## Code-server version

| Component | Version |
|-----------|---------|
| code-server | **v4.122.1** (submodule `code-server`) |
| VS Code | **1.122.1** |
| Node.js (RPM) | **22.22.0** (`nodejs:22` module) |

User-facing VS Code extensions (Python, Jupyter) are documented in
[`../Extensions.md`](../Extensions.md).

## Local build

Initialize the nested source checkout first:

```bash
git submodule update --init --recursive \
  codeserver-baseline/ubi9-python-3.12/code-server
```

Then build from the repository root:

```bash
uv sync --locked
make codeserver-baseline-pypi-3.12
```

For ODH local builds, `build-args/cpu.conf` supplies the baseline ODH settings.
The downstream RHOAI variant continues to use `build-args/konflux.cpu.conf`.

## Python lockfile flow

Phase 1 uses the public-index lock layout:

- `pyproject.toml` is the source of truth
- `pylock.toml` is generated in place at the image root
- `scripts/lockfile-generators/create-requirements-lockfile.sh` treats this
  directory as a `PUBLIC_INDEX_PROJECTS` entry

Regenerate after Python dependency changes:

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
  --pyproject codeserver-baseline/ubi9-python-3.12/pyproject.toml \
  --flavor cpu
```

## CI and Konflux

- ODH PR, main-push, and stable-push PipelineRuns live under `.tekton/`
- Manual PR trigger: `/build-codeserver-baseline`
- Phase 1 ODH Konflux builds are configured as non-hermetic (`hermetic: 'false'`)
- Phase 1 build-platform coverage is currently limited to `amd64`

## Phase 2 follow-up

The later hermetic conversion is expected to restore:

- `prefetch-input/` ownership and Cachi2 wiring
- flavor-specific `uv.lock.d/pylock.<flavor>.toml` and `requirements.<flavor>.txt`
- broader multi-arch code-server build support
