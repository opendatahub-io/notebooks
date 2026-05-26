# Skill: Scan Jira for Bugs

Fetch bugs from Jira using JQL and save to the triage ledger.

## Inputs

- `$ARGUMENTS`: optional JQL override or single issue key.
  - If omitted, use the default from `reference/jql-queries.md`.
  - If it looks like a single issue key such as `RHAIENG-3611`, normalize it to `key = RHAIENG-3611`.
  - Otherwise treat it as raw JQL.

## Procedure

1. **Determine JQL**:
   - if `$ARGUMENTS` is empty, use the **Canonical Default Triage Queue** from `reference/jql-queries.md`
   - if `$ARGUMENTS` looks like a single issue key (`PROJECT-123`), rewrite it to `key = PROJECT-123`
   - otherwise use `$ARGUMENTS` as raw JQL

2. **Get cloud ID**: call `mcp__atlassian__getAccessibleAtlassianResources` and extract the cloud ID for `redhat.atlassian.net`.

3. **Search**: call `mcp__atlassian__searchJiraIssuesUsingJql` with the JQL and cloud ID. Paginate if needed (the API returns up to ~50 results per call).

4. **Extract fields** for each issue:
   - `key` (e.g., RHAIENG-3611)
   - `summary`
   - `status` (New, Backlog, etc.)
   - `priority` (Blocker, Critical, Major, Normal, Minor)
   - `assignee` (displayName or null)
   - `labels` (existing labels array)
   - `created`, `updated`
   - `webUrl`

5. **Write ledger**: merge results into `.artifacts/triage/ledger.json` by issue key.
   - Preserve existing entries for issues already present in the ledger.
   - Preserve existing `triageStatus` and `assessment` for issues that were already assessed.
   - New issues discovered by the scan should be appended with `triageStatus: "pending"` and `assessment: null`.
   - Existing issues that are no longer returned by the current JQL should remain in the ledger; scan is cumulative state, not a destructive replace.
   - Supported `triageStatus` values:
     - `pending` — discovered but not yet assessed in this ledger
     - `assessed` — assessed in this ledger with a structured `assessment`
     - `previously-assessed` — already triaged before the current run; may rely on Jira labels/comments and can have `assessment: null`
     - `error` — triage attempted but the assessment/update failed; include an error note if available

   The ledger stores an array of objects like:
   ```json
   [
     {
       "key": "RHAIENG-3611",
       "summary": "Feast CLI fails with ModuleNotFoundError...",
       "status": "Backlog",
       "priority": "Blocker",
       "assignee": null,
       "labels": [],
       "created": "2026-03-06",
       "updated": "2026-03-20",
       "webUrl": "https://redhat.atlassian.net/browse/RHAIENG-3611",
       "triageStatus": "pending",
       "assessment": null
     }
   ]
```
   Create the `.artifacts/triage/` directory if it doesn't exist.

6. **Report**: print a summary table:
```sql
   Scanned N bugs from RHAIENG (component=Notebooks, active, not yet ai-triaged)
   Blocker: X | Critical: Y | Major: Z | Normal: W | Minor: V
   Saved to .artifacts/triage/ledger.json
```

## Next Step

Suggest running `/triage-assess` to analyze fixability, or `/triage-run` for end-to-end.
