# Skill: Implement the Fix

Apply the minimal code change to resolve the bug.

## Inputs

Continues from `skills/diagnose.md`. Root cause analysis is in `.artifacts/bugfix/{key}/root-cause.md`.

## Procedure

### 1. Create Feature Branch

```bash
git checkout -b fix/{key}-{short-description}
```

Use lowercase, kebab-case for the description (e.g., `fix/rhaieng-3611-pyarrow-s3fs`).

### 2. Implement Changes

Follow the recommended fix from the root cause analysis. Key conventions from `AGENTS.md`:

- **Python**: PEP 8, type hints, Python 3.14 syntax (PEP 758 `except ExcA, ExcB:` without parens when no `as`). Run `ruff format` mentally.
- **Dockerfiles**: minimize layers, keep Dockerfile.cpu and Dockerfile.konflux.cpu in sync
- **Dependencies**: edit pyproject.toml, then `gmake refresh-lock-files`
- **Manifests**: keep odh/ and rhoai/ variants consistent
- **Tests**: mirror source layout (`scripts/cve/` -> `tests/unit/scripts/cve/`)

### 3. Minimal Diffs Only

- Change only what's needed to fix the bug
- Don't refactor surrounding code
- Don't add comments, docstrings, or type annotations to unchanged code
- Don't "improve" adjacent logic

### 4. Regenerate Derived Files

If **dependencies changed** (pyproject.toml, cve-constraints.txt):
```bash
gmake refresh-lock-files
# Or targeted:
./uv run scripts/pylocks_generator.py auto jupyter/datascience/ubi9-python-3.12
```

If **manifests changed** (imagestream YAML, .env files):
```bash
./uv run manifests/tools/generate_kustomization.py
```

### 5. Show Diff

```bash
git diff
```

Present the diff to the user.

### 6. HITL Checkpoint

Wait for user confirmation before proceeding to `skills/test.md`.

### 7. Stage Changes

```bash
git add <specific-files>
```

Stage only the files that are part of the fix. Never `git add -A`.
