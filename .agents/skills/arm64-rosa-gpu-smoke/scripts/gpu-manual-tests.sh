#!/usr/bin/env bash
# Run ODH tests/manual GPU notebooks on all ARM CUDA images.
# See ../SKILL.md Phase 3b. Uses non-interactive exec (oc exec -q equivalent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO_ROOT"
exec uv run "$ROOT/scripts/gpu-manual-tests.py" "$@"
