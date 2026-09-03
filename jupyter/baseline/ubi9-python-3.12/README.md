# jupyter/baseline/ubi9-python-3.12

Hermetic baseline Jupyter workbench image with Python 3.12 on UBI 9.

## Status

- RPMs and Python packages are installed from Cachi2 prefetch inputs.
- Installs Python packages from `requirements.${PYLOCK_FLAVOR}.txt` with
  `--no-index --find-links /cachi2/output/deps/pip`.
- Keeps JupyterLab feature set (Elyra, Kale, PDF export) with a lean Python footprint.
- **Multi-arch**: Konflux builds all four Linux arches; JupyterLab/Elyra/Kale Python deps
  install on **x86_64 + aarch64 only** (PyPI wheel gap on ppc64le/s390x), using explicit
  ``platform_machine == 'x86_64' or == 'aarch64'`` allowlist markers. Other arches receive
  uv, wheel, setuptools, micropipenv, packaging, and pip. See `[tool.uv] environments`
  and `required-environments` in `pyproject.toml`.

## Local build

```bash
uv sync --locked
make jupyter-baseline-ubi9-python-3.12
```

For ODH local builds, `build-args/cpu.conf` uses the c9s `odh-base-image-cpu`
(`quay.io/opendatahub/odh-base-image-cpu-py312-c9s`). The downstream RHOAI
variant continues to use `build-args/konflux.cpu.conf`.

## Python lockfile flow

- `pyproject.toml` is the source of truth
- `pylock.toml` is generated in place at the image root
- `requirements.cpu.txt` is generated from that `pylock.toml` (pip/Cachi2 format; default `el9-fallback` omits sdist hashes when EL9 wheels exist)
- `make refresh-lock-files` and `create-requirements-lockfile.sh` detect this
  layout automatically
- Dockerfiles install with `uv pip install --no-index --find-links /cachi2/output/deps/pip`

Regenerate after Python dependency changes:

```bash
./scripts/lockfile-generators/create-requirements-lockfile.sh \
  --pyproject-toml jupyter/baseline/ubi9-python-3.12/pyproject.toml \
  --flavor cpu
```

## CI and Konflux

- ODH PR and push PipelineRuns live under `.tekton/` (`*-c9s-pull-request.yaml` / `*-c9s-push.yaml`)
- PR pipelines path-filter to this image (plus `jupyter/utils` and `start-notebook.sh`); they do not run on every PR
- Manual PR trigger: `/build-jupyter-baseline` (also `/build-konflux` / `/kfbuild-all`)
- ODH Konflux builds are hermetic (`hermetic: 'true'`) with RPM, generic, and pip prefetch
- Push builds (stable / `opendatahub-builds`) publish `odh-stable` and `3.6_ea2-v1.49` to `quay.io/opendatahub/odh-workbench-jupyter-baseline-cpu-py312-c9s`
