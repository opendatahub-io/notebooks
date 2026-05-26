# Skill: Read an internal Google Doc (`gws`)

Use this when you need **machine-readable text** from a Google Doc (e.g. program runbooks, label tables) that is not available via public fetch.

## Prerequisites

- **`gws`** installed and authenticated (`which gws`). See `prerequisites.md` §15.
- Run **`gws` outside a sandboxed environment** if token/keyring cache errors appear (`Operation not permitted` on keyring).

## Fetch JSON (API shape)

```bash
gws docs documents get --params '{"documentId":"<ID>","includeTabsContent":true}' --format json
```

Document ID: from the URL `https://docs.google.com/document/d/<ID>/edit`.

## Convert to markdown (repo helper)

From the **repository root**:

```bash
python .agents/tools/fetch_google_doc.py '<document-id-or-url>' -o /tmp/doc.md
```

Script: [`.agents/tools/fetch_google_doc.py`](../../tools/fetch_google_doc.py)

## Canonical bug-bash reference

- [AI First Bug Bash](https://docs.google.com/document/d/1aLED1gER-YINBjCHp5mUg5ChQf4BNpdRlnoEBKs_RF8/edit) — outcome labels are mirrored in `triage/reference/label-taxonomy.md`.
