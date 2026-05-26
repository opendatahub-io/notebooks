# .artifacts/

Working directory for AI agent workflows. Contents are gitignored except this file.

## Structure

- `sbom/` — Downloaded manifestbox SBOM JSON files (~8MB each). Used by `scripts/cve/sbom_analyze.py` for CVE triage.
- `triage/` — Triage session state (`ledger.json`).
- `bugfix/{key}/` — Per-issue bugfix artifacts (`root-cause.md`, `context.md`, `test-failures.md`).