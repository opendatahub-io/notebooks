---
name: uv-resolver-gotchas
description: uv resolver behavior, lock file refresh pitfalls, and worktree naming for tests
paths:
  - "**/pyproject.toml"
  - "**/pylock*.toml"
  - "**/requirements*.txt"
  - "**/pylocks_generator.py"
  - "**/cve-constraints.txt"
---

# uv Resolver and Lock File Gotchas

## PubGrub does not guarantee highest versions

uv uses PubGrub (via pubgrub-rs). `--upgrade` makes it *try* highest first,
but the solver backtracks on conflicts and may settle on older versions.
Adding an unrelated constraint (e.g. `setuptools<81`) can cascade into a
completely different solution for other packages (e.g. llmcompressor
dropping from 0.12.0 to 0.10.0.2). This is documented in
[uv resolver internals](https://docs.astral.sh/uv/reference/internals/resolver/).

**Always pin lower bounds** (`>=`) on packages that must not regress. The
`test_pylock_downgrade` test catches regressions vs `origin/main`.

## Lock refresh pipeline

After `make refresh-lock-files`, always run the full regen pipeline before
`make test`:

```bash
uv run scripts/dockerfile_fragments.py
uv run manifests/tools/generate_kustomization.py
uv run python manifests/tools/update_imagestream_annotations_from_pylock.py --variant odh
uv run python manifests/tools/update_imagestream_annotations_from_pylock.py --variant rhoai
```

The CI workflow (`piplock-renewal.yaml`) does all of these.

## Worktree naming

`is_image_directory()` in `tests/test_main.py` matches any directory name
with exactly three hyphen-separated parts (like `ubi9-python-3.12`).
Worktree names like `notebooks-fix-manifests` collide. Use underscores
(`notebooks_fix_manifests`) or other non-colliding names.

## Constraint placement

- `dependencies/constraints.txt` -- CVE-driven **minimum** version floors, applied globally
- `dependencies/overrides.txt` -- forced package versions (overrides inter-package dependencies), applied globally
- `dependencies/odh-notebooks-meta-*-deps/pyproject.toml` -- scoped constraints for a dependency group (preferred for non-CVE caps like `setuptools<81`)
- `override-dependencies` in image `pyproject.toml` -- last resort for unresolvable transitive conflicts
