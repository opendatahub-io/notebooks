# runtimes/baseline/ubi9-python-3.12

Hermetic baseline Elyra pipeline runtime image with Python 3.12 on UBI 9.

## Status

- RPMs and Python packages are installed from Cachi2 prefetch inputs.
- Installs Python packages from `requirements.${PYLOCK_FLAVOR}.txt` with
  `--no-index --find-links /cachi2/output/deps/pip`.
- Keeps Elyra/Kale execution capability with a lean Python footprint (no
  datascience / DB-connector stack).

## Local build

```bash
uv sync --locked
make runtime-baseline-ubi9-python-3.12
```

For ODH local builds, `build-args/cpu.conf` supplies the baseline ODH settings.
The downstream RHOAI variant continues to use `build-args/konflux.cpu.conf`.

## Python lockfile flow

- `pyproject.toml` is the source of truth
- `pylock.toml` is generated in place at the image root
- `requirements.cpu.txt` is generated from that `pylock.toml` (pip/Cachi2 format)
- `make refresh-lock-files` and `create-requirements-lockfile.sh` detect this
  layout automatically
- Dockerfiles install with `uv pip install --no-index --find-links /cachi2/output/deps/pip`

Regenerate after Python dependency changes:

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
  --pyproject-toml runtimes/baseline/ubi9-python-3.12/pyproject.toml \
  --flavor cpu
```

Or:

```bash
make refresh-lock-files INDEX_MODE=public-index DIR=runtimes/baseline/ubi9-python-3.12
```

## CI and Konflux

- ODH PR PipelineRuns live under `.tekton/` (`*-c9s-pull-request.yaml`)
- Manual PR trigger: `/build-runtime-baseline`
- ODH Konflux builds are hermetic (`hermetic: 'true'`) with RPM, generic, and pip prefetch
