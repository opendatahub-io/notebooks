# ntb/ — Shared Python library

Small utility library used across CI scripts and tests. Installed as the `notebooks` package via `uv sync`.

## Modules

- `__init__.py` — Re-exports key functions (`assert_subdict`)
- `asserts.py` — Custom assertion helpers for tests
- `constants.py` — Shared constants
- `strings.py` — Template processing, string manipulation, blockinfile operations
