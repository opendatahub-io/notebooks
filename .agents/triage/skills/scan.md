# Skill: Scan Jira for Bugs

Fetch bugs from Jira using JQL and save to the triage ledger.

## Inputs

- `$ARGUMENTS`: optional JQL override. If not provided, use the default from `reference/jql-queries.md`.

## Procedure

1. **Determine JQL**: if `$ARGUMENTS` contains a JQL string, use it. Otherwise use:
   ```jql
   project = RHAIENG AND statusCategory not in (Done)
   AND issuetype in (Bug) AND component = Notebooks
   AND (labels not in (ai-triaged) OR labels is EMPTY)
   ORDER BY priority DESC, updated DESC
   ```

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

5. **Write ledger**: save results to `.artifacts/triage/ledger.json` as an array of objects:
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
   ```
   Scanned N bugs from RHAIENG (component=Notebooks, not Done, not yet triaged)
   Blocker: X | Critical: Y | Major: Z | Normal: W | Minor: V
   Saved to .artifacts/triage/ledger.json
   ```

## Next Step

Suggest running `/triage-assess` to analyze fixability, or `/triage-run` for end-to-end.
