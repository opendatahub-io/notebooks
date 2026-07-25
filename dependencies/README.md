# Global lock inputs

Image lock files (`uv.lock.d/pylock.*.toml`) are generated with three layers of
dependency rules:

| Layer | File | uv flag | Purpose |
|-------|------|---------|---------|
| 1 | `constraints.txt` | `--constraints` | Global version **floors** (`package>=X`) |
| 2 | `overrides.txt` | `--override` | Global **forced pins/ranges** when a floor is insufficient; **replaces** package-declared requirements (runtime risk — see below) |
| 3 | `pyproject.toml` `[tool.uv.override-dependencies]` | (from pyproject) | **Image-specific** overrides |

Both global files are always passed to `uv pip compile`, even when empty.

**Prefer `constraints.txt` over `overrides.txt`.** Put shared rules in these
`.txt` files; put subset-specific rules in individual `pyproject.toml` files.

See [docs/cves/python.md](../docs/cves/python.md) for the CVE resolution workflow.

## `constraints.txt`

Two sections:

- **`# --- CVE-motivated floors ---`** — minimum versions for security fixes
- **`# --- General floors ---`** — non-CVE policy or resolver floors

Formatting rules (keep the file short):

- **One line per package** — only the most restrictive floor currently in effect.
- **One comment per package** — cite the Jira/CVE that motivated the *current* floor.
  Do not maintain a historical ledger of superseded fixes.
- When a new CVE requires a higher floor, replace the old line and update the comment.

### Branch policy

| Repo / branch | Role of `constraints.txt` |
|---------------|---------------------------|
| `opendatahub-io/notebooks` `main` | Lock-renewal auto-syncs with the latest AIPCC Python index. Once a fixed version is available on AIPCC, lock renewal picks it up without a new constraint. Do not add CVE constraints on `main` solely to track a fix the index already ships. |
| `red-hat-data-services/notebooks` `rhoai-x.y` | Audit proof of what the release enforces. Keep updating when backporting CVE fixes, even when `main` already absorbed the fix via index sync. |

On `main`, constraints are for floors the resolver/index sync alone cannot
guarantee. On `rhoai-x.y`, constraints also record CVE remediation for the release.

## `overrides.txt`

Forced pins or ranges that `constraints.txt` cannot express, or that lose in resolver
conflicts. Keep this file smaller than `constraints.txt`.

**Runtime risk:** `uv --override` replaces package-declared requirements rather than
adding a bound. A successful lock resolution therefore does **not** guarantee the
forced version works at runtime with every image's dependency tree. Before adding a
global entry, require compatibility evidence (tests, upstream guidance, or a
deliberate all-image audit) — this file applies to **every** image.

**Review obligation:** every time you touch this file, carefully review all entries
for obsolete, broken, or dangerous pins. Fix or remove anything no longer justified
immediately.

Per-entry comments cite the Jira/issue that motivated the pin.
