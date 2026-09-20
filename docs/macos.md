# macOS Development Notes

## Syft exclude paths broken under `/tmp`

macOS symlinks `/tmp` → `/private/tmp`. Syft resolves the real path when indexing files but matches exclude patterns against the user-provided path. This mismatch causes all `exclude:` patterns to silently fail when scanning a directory under `/tmp`.

**Workaround**: Run syft from a non-symlinked path (e.g. `~/`, the repo checkout, or `/private/tmp/` directly).

This does not affect CI (Linux) or the repo's `.syft.yaml` (which is in the repo root, not under `/tmp`).
