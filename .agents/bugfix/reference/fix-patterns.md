# Common Fix Patterns for OpenDataHub Notebooks

Patterns observed in past fixes. Follow these when implementing bugfixes.

## 1. Dependency Version Bump

**When**: CVE fix, compatibility issue, package update request.

```bash
# Edit the dependency constraint
vi jupyter/datascience/ubi9-python-3.12/pyproject.toml

# Regenerate lock files
gmake refresh-lock-files
# Or targeted:
./uv run scripts/pylocks_generator.py auto jupyter/datascience/ubi9-python-3.12

# Verify
make test
```

**Key points**:
- Understand the image inheritance chain (minimal -> datascience -> specialized)
- A change in a parent image's dependencies affects all children
- Always regenerate lock files — manual lock file edits break reproducibility

## 2. Dockerfile Layer Fix

**When**: Build failure, missing package, wrong base image, COPY path error.

**Key points**:
- Keep `Dockerfile.cpu` and `Dockerfile.konflux.cpu` (and other variants) in sync
- Minimize layers — combine RUN commands where logical
- Follow existing patterns for package installation (dnf for RPMs, pip/uv for Python)
- Check both KONFLUX=yes and KONFLUX=no build paths

## 3. Manifest Tag Update

**When**: Wrong image deployed, version mismatch, missing notebook option.

**Files**: `manifests/odh/base/*.yaml`, `manifests/rhoai/base/*.yaml`

**Key points**:
- `params-latest.env` contains image digests
- ImageStream YAML files define available notebook options
- Changes must be consistent between odh/ and rhoai/ variants
- After changing `.env` files or ImageStreams: `./uv run manifests/tools/generate_kustomization.py`
- To query Pyxis catalog for image tags/digests: `./uv run manifests/tools/generate_envs.py --version-tag v3.3`

## 4. Test Fixture Fix

**When**: Test failure due to wrong assertion, missing fixture, outdated test data.

**Key points**:
- Mirror source layout: `scripts/cve/` -> `tests/unit/scripts/cve/`
- Run specific tests: `./uv run pytest tests/unit/ -k "test_name"`
- Follow Python 3.14 conventions (PEP 758 exception syntax)

## 5. Script / CI Fix

**When**: CI pipeline failure, script error, wrong automation behavior.

**Files**: `scripts/`, `ci/`, `.tekton/`, `.github/workflows/`

**Key points**:
- Scripts are Python 3.14 — use modern syntax
- Run `./uv run ruff check` and `./uv run pyright` after changes
- Some Tekton YAML is auto-generated — check if there's a generator script

## 6. Nginx / Server Config Fix

**When**: Proxy issues, routing errors, static file serving problems in Code Server or RStudio.

**Files**: `codeserver/*/nginx/`, `rstudio/*/nginx/`

**Key points**:
- Test with container build and startup
- Check both HTTP and HTTPS paths
- Verify reverse proxy headers are forwarded correctly
