# A Guide to Python Package Management with `uv`

[`uv`](https://docs.astral.sh/uv/) is a fast Python package installer and resolver. This
repository uses it for both local development and per-image lock file generation.

**Contributors should not run raw `uv pip compile` against image `pyproject.toml` files
by default.** Use the repository wrapper tooling described below; it applies global
constraints, resolves the correct Red Hat or public index per image, and writes lock
files in the layout CI expects.

For the quick path when changing dependencies, see also
[`CONTRIBUTING.md`](../CONTRIBUTING.md) and [`docs/packageupdate.md`](packageupdate.md).
For CVE-driven lockfile work, see [`docs/cves/python.md`](cves/python.md).

---

## 1. Recommended workflow: `make refresh-lock-files`

Regenerate image lock files after editing any `pyproject.toml`, global constraint file,
or lock generator script:

```bash
# All images, auto-detected index mode (default)
make refresh-lock-files

# One image directory
make refresh-lock-files DIR=jupyter/minimal/ubi9-python-3.12

# Force a specific index mode
make refresh-lock-files INDEX_MODE=rh-index
make refresh-lock-files INDEX_MODE=public-index

# Upgrade all packages to the latest compatible versions (release kickoff, broad bumps)
FORCE_LOCKFILES_UPGRADE=1 make refresh-lock-files
```

The Makefile target runs `uv run scripts/pylocks_generator.py` with the selected
`INDEX_MODE` and optional `DIR`. Image lock generation uses the pinned `./uv` wrapper
(`dependencies/uv-image-lock-version`, currently stricter than the dev-tooling uv pin
in root `pyproject.toml`). See [Dual `uv` versions](#dual-uv-versions) below.

### Makefile variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INDEX_MODE` | `auto` | Lock index selection: `auto`, `rh-index`, or `public-index` |
| `DIR` | *(empty)* | Limit regeneration to one project directory |
| `FORCE_LOCKFILES_UPGRADE` | `0` | Set to `1` to pass `--upgrade` during lock generation |
| `UV_EXTRA_INDEX_URL` / `PIP_EXTRA_INDEX_URL` | *(unset)* | Optional extra indexes forwarded only to lock generation (for example RH CUDA `*-test/simple/` wheels). The Makefile maps these to `UV_LOCK_EXTRA_INDEX_URL` / `PIP_LOCK_EXTRA_INDEX_URL` so root `uv run` is unaffected. |

---

## 2. Index modes

`scripts/pylocks_generator.py` supports three modes. `auto` is the default.

| Mode | When used | Index source | Lock output |
|------|-----------|--------------|-------------|
| `auto` | Default | `rh-index` when `uv.lock.d/` exists in the project; otherwise `public-index` | Per-mode layout below |
| `rh-index` | RHOAI / AIPCC images with `build-args/konflux.<flavor>.conf` | Red Hat wheel indexes resolved from `build-args/` via `scripts/index_url_resolver.py` | `uv.lock.d/pylock.<flavor>.toml` and `requirements.<flavor>.txt` |
| `public-index` | ODH baseline images (`jupyter/baseline`, `codeserver-baseline`, `runtimes/baseline`, and similar) | Public PyPI | Root `pylock.toml` and `requirements.cpu.txt` |

Direct script invocation (equivalent to the Makefile target):

```bash
uv run scripts/pylocks_generator.py                         # auto, all images
uv run scripts/pylocks_generator.py rh-index jupyter/minimal/ubi9-python-3.12
uv run scripts/pylocks_generator.py public-index jupyter/baseline/ubi9-python-3.12
uv run scripts/pylocks_generator.py --requirements-only     # convert existing pylock → requirements only
```

### Lock file layout

**RH-index images** (most workbench and runtime images):

```text
jupyter/datascience/ubi9-python-3.12/
├── pyproject.toml
├── uv.lock.d/
│   ├── pylock.cpu.toml
│   ├── pylock.cuda.toml      # when Dockerfile.konflux.cuda exists
│   └── pylock.rocm.toml      # when Dockerfile.konflux.rocm exists
├── requirements.cpu.txt
├── requirements.cuda.txt
└── requirements.rocm.txt
```

**Public-index images** (baseline layouts):

```text
jupyter/baseline/ubi9-python-3.12/
├── pyproject.toml
├── pylock.toml
└── requirements.cpu.txt
```

RH-index mode runs `uv pip compile --universal` (multi-arch wheel selection).
Public-index mode runs `uv lock` + `uv export --format pylock.toml` so
`[tool.uv] required-environments` and environment markers in `pyproject.toml` are
honored.

---

## 3. Global dependency inputs

Every lock generation passes shared rules from `dependencies/`:

| File | uv flag | Purpose |
|------|---------|---------|
| `dependencies/constraints.txt` | `--constraints` | Global version **floors** (`package>=X`), including CVE-motivated floors |
| `dependencies/overrides.txt` | `--override` | Global **forced pins/ranges** when a floor is insufficient |
| `pyproject.toml` `[tool.uv.override-dependencies]` | *(from pyproject)* | Image-specific overrides |

See [`dependencies/README.md`](../dependencies/README.md) and
[`docs/cves/python.md`](cves/python.md) for format rules and CVE workflow. After adding
a constraint, rerun `make refresh-lock-files`.

### Meta-package exclusion

Shared dependency groups live under `dependencies/odh-notebooks-meta-*-deps/` as
`package = false` meta-packages. The lock generator passes `--no-emit-package` for
these names so they group dependencies in `pyproject.toml` but do not appear as pinned
entries in `pylock.toml`. Tests enforce this exclusion.

### CUDA / ROCm index fallback

For `rh-index` mode, `scripts/index_url_resolver.py` selects the Red Hat wheel index
from each image's `build-args/konflux.<flavor>.conf`:

- Non-release runs may try the matching `-test` index when production is unavailable.
- Release lock generation must fail when the production index is unavailable.
- For ROCm images, may also try the stable release stream before the configured EA
  release.
- Appends `?format=json` to RH index URLs so Pulp returns PEP 691 metadata (needed
  for reproducible `--exclude-newer` cutoffs).

Optional extra indexes for lock generation only:

```bash
UV_EXTRA_INDEX_URL='https://packages.redhat.com/.../cuda13.0-ubi9-test/simple/' \
  make refresh-lock-files INDEX_MODE=rh-index DIR=jupyter/pytorch/ubi9-python-3.12
```

---

## 4. Dual `uv` versions

| Context | uv pin | How to invoke |
|---------|--------|---------------|
| Repo dev tooling (tests, pre-commit, `uv sync`) | `>=0.11.8,<0.13` in root `pyproject.toml` | System `uv` after `uv sync --locked` |
| Image lock files | Exact version in `dependencies/uv-image-lock-version` | `make refresh-lock-files` or `./uv run scripts/pylocks_generator.py …` |

Do not use `./uv` for everyday development unless you are refreshing image locks.

---

## 5. Script reference

| Script / target | Role |
|-----------------|------|
| `make refresh-lock-files` | **Primary entry point** for contributors |
| `scripts/pylocks_generator.py` | Generates `pylock.toml` / `uv.lock.d/` and `requirements.*.txt` |
| `scripts/index_url_resolver.py` | Resolves RH index URLs from `build-args/` |
| `scripts/lockfile-generators/create-requirements-lockfile.sh` | Full hermetic prefetch pipeline (pylock + requirements + wheel download for Cachi2). Used by subscribed builds; not needed for routine dependency bumps. |
| `scripts/lockfile-generators/helpers/pylock-to-requirements.py` | Converts PEP 751 `pylock.toml` to pip-compatible `requirements.<flavor>.txt` |

CI runs `PYLOCKS_CI_CHECK=1 uv run scripts/pylocks_generator.py auto --pr-base origin/<base>`
to regenerate only images whose lock chain changed in a PR. Local contributors normally
run `make refresh-lock-files` without that flag.

---

## 6. Troubleshooting

| Symptom | Likely cause | What to try |
|---------|--------------|-------------|
| `unsatisfiable` / version conflict during lock regen | Conflicting floors in `constraints.txt`, `overrides.txt`, or `pyproject.toml` | Read the resolver error; adjust constraints or add image-specific `[tool.uv.override-dependencies]` (see [`docs/cves/python.md`](cves/python.md)) |
| RH index not found | EA index not published yet for the accelerator/release | Retry later; for CUDA wheels sometimes set `UV_EXTRA_INDEX_URL` to the `*-test/simple/` index |
| Transient 5xx from RH index | Flaky index during compile | Re-run `make refresh-lock-files` (generator retries transient failures) |
| `check-generated-code` fails on pylock drift | Lock files not regenerated after dependency edits | `make refresh-lock-files` (or scope with `DIR=`) and commit the updated lock files |
| macOS vs Linux header differences | Absolute paths in lock headers | Use `make refresh-lock-files`; the generator writes repo-relative paths |
| Meta-package appears in `pylock.toml` | Missing `--no-emit-package` for a new `odh-notebooks-meta-*-deps` package | Add the name to `NO_EMIT_PACKAGES` in `scripts/pylocks_generator.py` |

---

## 7. Advanced: low-level `uv` usage

The sections below describe `uv` concepts and manual commands. Use them to understand
how the wrapper tooling works, or for experiments outside the image lock pipeline.

### Adding packages (root dev environment)

Packages for the **repository test tooling** (not image dependencies) can be added
with `uv add` against the root `pyproject.toml`:

```bash
uv add requests              # latest compatible release
uv add 'requests~=2.25'      # latest 2.25.* release
uv add beautifulsoup4 lxml   # multiple packages
uv add requests --group group1
```

Image dependencies belong in each image's `pyproject.toml` under the appropriate
`[dependency-groups]` entry, followed by `make refresh-lock-files`.

### Manual compile (RH-index layout)

RH-index lock files are produced with `uv pip compile --universal`, not
`--python-platform linux` (which targets a single platform). Example equivalent to
what the generator runs for one flavor:

```bash
cd jupyter/datascience/ubi9-python-3.12
../../../uv pip compile pyproject.toml \
  --output-file uv.lock.d/pylock.cpu.toml \
  --format pylock.toml \
  --generate-hashes \
  --emit-index-url \
  --python-version=3.12 \
  --universal \
  --no-annotate \
  --constraints ../../../dependencies/constraints.txt \
  --override ../../../dependencies/overrides.txt \
  --default-index='https://packages.redhat.com/api/pypi/public-rhai/rhoai/…/cpu-ubi9/simple/'
```

Prefer `make refresh-lock-files` so index URLs, `--no-emit-package`, and
`requirements.<flavor>.txt` conversion stay consistent.

### Installing from a locked file

```bash
uv pip sync requirements.cpu.txt
```

Image Dockerfiles install from `pylock.toml` via the `./uv` wrapper with
`UV_PREVIEW_FEATURES=pylock`.

### Resolving conflicts

Dependency conflicts occur when packages require incompatible versions. When
`uv lock`, `uv pip install`, or `uv pip compile` cannot find a solution, read the
resolver error carefully — it names the conflicting packages and version ranges.

**Strategies:**

1. **Review error messages** — identify which direct dependency pins conflict.
2. **Use `uv` groups and `[tool.uv].conflicts`** — isolate incompatible dependency
   sets that are never installed together:
   ```toml
   [dependency-groups]
   group1 = ["package_A==1.0"]
   group2 = ["package_B>=2.0"]

   [tool.uv]
   conflicts = [
       [{ group = "group1" }, { group = "group2" }],
   ]
   ```
3. **Use environment markers (PEP 508)** for platform- or Python-version-specific deps.
4. **Use `[tool.uv.dependency-metadata]`** to override transitive requirements when
   metadata is wrong (last resort).
5. **Adjust global constraints** — for image-wide floors or overrides, prefer
   `dependencies/constraints.txt` and `dependencies/overrides.txt` so
   `make refresh-lock-files` applies them everywhere.

---

## Related documentation

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — local setup and `make test`
- [`docs/packageupdate.md`](packageupdate.md) — version bump procedure
- [`docs/cves/python.md`](cves/python.md) — CVE constraints and lock regen
- [`dependencies/README.md`](../dependencies/README.md) — global lock input files
- [`scripts/lockfile-generators/README.md`](../scripts/lockfile-generators/README.md) — hermetic prefetch pipeline
