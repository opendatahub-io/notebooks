# runtimes/baseline/ubi9-python-3.12

Phase 1 baseline Elyra pipeline runtime image with Python 3.12 on UBI 9.

## Status

- Resolves RPM and Python dependencies online during the image build.
- Installs Python packages from the checked-in root `pylock.toml` using PyPI.
- Keeps Elyra/Kale execution capability with a lean Python footprint (no
  datascience / DB-connector stack).
- Keeps hermetic `prefetch-input/` conversion deferred to phase 2.

## Local build

```bash
uv sync --locked
make runtime-baseline-ubi9-python-3.12
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
  --pyproject runtimes/baseline/ubi9-python-3.12/pyproject.toml \
  --flavor cpu
```

Or:

```bash
make refresh-lock-files INDEX_MODE=public-index DIR=runtimes/baseline/ubi9-python-3.12
```

## CI and Konflux

- ODH PR, main-push, and stable-push PipelineRuns live under `.tekton/`
- Manual PR trigger: `/build-runtime-baseline`
- Phase 1 ODH Konflux builds are configured as non-hermetic (`hermetic: 'false'`)

## Phase 2 follow-up

The later hermetic conversion is expected to restore:

- `prefetch-input/` ownership and Cachi2 wiring
- flavor-specific `uv.lock.d/pylock.<flavor>.toml` and `requirements.<flavor>.txt`
