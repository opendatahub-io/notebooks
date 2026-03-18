# ci/ — Continuous Integration utilities

This directory contains Python scripts used by GitHub Actions workflows and the Makefile build system.

## Key modules

- `cached-builds/` — Logic for determining which images need rebuilding based on changed files
  - `gha_pr_changed_files.py` — Detects changed files in PRs to skip unchanged image builds
  - `gen_gha_matrix_jobs.py` — Generates GitHub Actions matrix job configurations
  - `makefile_helper.py` — Wraps `make` dry-run to extract build variables
  - `konflux_generate_component_*.py` — Generates Konflux/Tekton pipeline definitions
- `check-software-versions.py` — Validates package versions inside built images against expectations
- `validate_json.py` — Validates JSON files across the repository
- `package_versions.py` — Parses and compares Python package version specifications
