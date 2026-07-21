---
description: Fix CVE vulnerabilities in the Notebooks repository
---

# /fix-cve - CVE Resolution Command

## Purpose

Execute the **complete CVE resolution workflow** autonomously — from assignment through fix, PR creation, Jira updates, logging, and Slack summary. **No questions asked.**

## Prerequisites

- Jira MCP configured — see [docs/claude-mcp.md](../../docs/claude-mcp.md)
- GitHub access for PR creation
- Write access to the notebooks repository
- Full guide: [docs/cves/cve-developer-guide.md](../../docs/cves/cve-developer-guide.md)

## Usage

```
/fix-cve                      # Full workflow - assign AND fix top CVEs
/fix-cve plan                 # Same as above - full workflow
/fix-cve <TICKET-ID>          # Fix a specific CVE ticket
/fix-cve status               # Show status of assigned CVEs
```

---

## ⚠️ CRITICAL: FULLY AUTONOMOUS EXECUTION

**THIS IS THE MOST IMPORTANT SECTION. FOLLOW EXACTLY.**

### NEVER Ask Questions - Just Execute

When this command is invoked, execute the **ENTIRE workflow** without stopping:

❌ **NEVER ASK:**
- "Would you like me to proceed?"
- "Should I assign these tickets?"
- "Would you like me to create a PR?"
- "Should I comment on Jira?"
- "Can I run this git command?"
- "Should I search the web for CVE info?"
- "Do you want me to run `git checkout`?"
- "Should I push to origin?"

✅ **JUST DO IT:**
- Run git commands directly
- Search web for CVE/package info directly
- Create PRs directly
- Comment on Jira directly
- Log results directly

### ALL Tools Pre-Approved

The following are **PRE-APPROVED** — execute without asking:

| Tool/Action | Status |
|-------------|--------|
| `git checkout -b` | ✅ Just run it |
| `git fetch` | ✅ Just run it |
| `git add` | ✅ Just run it |
| `git commit` | ✅ Just run it |
| `git push` | ✅ Just run it |
| `gh pr create` | ✅ Just run it |
| `make refresh-lock-files` | ✅ Just run it |
| Web search (CVE details) | ✅ Just search |
| Web search (package versions) | ✅ Just search |
| Read any file | ✅ Just read |
| Write constraints file | ✅ Just write |
| Write log file | ✅ Just write |
| Jira MCP (search) | ✅ Just call |
| Jira MCP (assign) | ✅ Just call |
| Jira MCP (comment) | ✅ Just call |

### Example: Correct Execution

```
✓ Fetching current sprint...
✓ Current Sprint: Notebooks - Narwal
✓ Searching for unassigned CVEs...
✓ Found 10 CVEs
✓ Assigning RHAIENG-4406 [rhoai-2.25]...
✓ Assigning RHAIENG-4458 [rhoai-3.3]...
✓ Checking out rds/rhoai-2.25...
✓ Creating branch fix/cve-2026-34986-tornado...
✓ Running make refresh-lock-files (RHOAI ≥3.4 auto-upgrade)...
✓ Verifying CVE resolved in lockfiles...
✓ CVE still present - adding constraint to cve-constraints.txt...
✓ Re-running make refresh-lock-files...
✓ Committing changes...
✓ Pushing to red-hat-data-services/notebooks...
✓ Creating PR to rhoai-2.25...
✓ PR #2550 created
✓ Commenting on RHAIENG-4406...
⚠️ CVE-2026-1462: Cannot fix - keras 3.8.0 not available (logged)
✓ Results logged to cve-resolution-log.md

✅ COMPLETE

📊 Summary: Fixed 8, Failed 2
📝 Slack message ready below
```

### When To Stop (ONLY These Cases)

1. **Fatal MCP error** — Cannot connect to Jira at all
2. **No CVEs found** — Nothing to process
3. **Unrecoverable git error** — Merge conflict that can't be auto-resolved

---

## Full Workflow: `/fix-cve` or `/fix-cve plan`

**Execute ALL 10 steps automatically:**

### Step 1: Find Current Sprint
```
Tool: searchJiraIssuesUsingJql
jql: project = RHAIENG AND component = Notebooks AND sprint in openSprints()
```
→ `✓ Sprint: Notebooks - Narwal`

### Step 2: Get Developer Account ID
```
Tool: getJiraUserProfile
```
→ `✓ User: [Name]`

### Step 3: Fetch Top 10 Unassigned CVEs
```
Tool: searchJiraIssuesUsingJql
jql: project = RHAIENG AND component = Notebooks AND labels IN (CVE) 
     AND status NOT IN (Closed, Resolved) AND assignee IS EMPTY 
     ORDER BY duedate ASC
limit: 12
```
→ Display table, then **immediately proceed to Step 4**

### Step 4: Assign ALL Tickets
```
For each ticket:
  Tool: editJiraIssue
  updateFields: { assignee: { accountId: "..." }, customfield_10020: sprintId }
```
→ `✓ Assigned 10 tickets`

### Step 5: Group CVEs by Package
Group same CVE ID across releases.
→ `✓ Grouped into X unique CVEs`

### Step 6: Fix Each CVE

**IMPORTANT:** RHAIENG CVE tickets must be fixed on the **downstream** repository
(`red-hat-data-services/notebooks`) on the release branch indicated in the ticket title.

Extract the target branch from the ticket title suffix (e.g., `[rhoai-2.25]` → `rhoai-2.25`).

**For EACH CVE (loop through all):**

1. **Determine target branch** from ticket title:
   - `[rhoai-2.25]` → branch `rhoai-2.25`
   - `[rhoai-3.3]` → branch `rhoai-3.3`
   - etc.

2. **Add remote if needed** (just do it):
   ```bash
   git remote add rds https://github.com/red-hat-data-services/notebooks.git 2>/dev/null || true
   git fetch rds
   ```

3. **Create branch from downstream release branch** (just do it):
   ```bash
   git checkout -b fix/cve-YYYY-NNNNN-package rds/rhoai-X.Y
   ```

4. **For RHOAI releases ≥3.4:** First try `make refresh-lock-files` to auto-upgrade packages.
   This often resolves CVEs automatically since we don't pin specific versions.

5. **Check if CVE is resolved** by verifying the package version in lockfiles.
   If NOT resolved (CVE in transitive dependency), add constraint:
   ```
   # RHAIENG-XXXX: CVE-YYYY-NNNNN description
   package>=X.Y.Z
   ```
   Then re-run `make refresh-lock-files`.

6. **For RHOAI releases <3.4:** Add constraint to `dependencies/cve-constraints.txt`:
   ```
   # RHAIENG-XXXX: CVE-YYYY-NNNNN description
   package>=X.Y.Z
   ```
   Then run `make refresh-lock-files`.

7. **If fix fails:** Log reason, continue to next CVE

8. **Commit** (just do it):
   ```bash
   git add dependencies/cve-constraints.txt */pylock.toml
   git commit -m "RHAIENG-XXXX: chore(deps): fix CVE-..."
   ```

9. **Push and create PR to downstream** (just do it):
   ```bash
   git push -u rds fix/cve-...
   gh pr create --repo red-hat-data-services/notebooks --base rhoai-X.Y --title "..." --body "..."
   ```

### Step 7: Comment on Jira Tickets
```
For each successful fix:
  Tool: addCommentToJiraIssue
  commentBody: "PR created: [URL]\nFix: Bumped package to version"
```

### Step 8: Log ALL Results
Append to `docs/cves/logs/cve-resolution-log.md`:
- All fixed CVEs with PR links
- All failed CVEs with research notes
- Summary stats

### Step 9: Generate Slack Message

**ALWAYS output this at the end:**

```
📝 Slack Message (copy and post to team channel):
───────────────────────────────────────────────
🔒 **CVE Resolution Update**

**Fixed (PRs created):**
• CVE-2026-34986 (go-jose) - PR #4100
• CVE-2026-1462 (keras) - PR #4101
[list all]

**Unable to fix (needs manual review):**
• CVE-2026-XXXXX (package) - [reason]
[list all failures]

**PRs ready for review:**
https://github.com/red-hat-data-services/notebooks/pulls?q=is%3Aopen+author%3A[user]

Please review when you have a chance. Thanks! 🙏
───────────────────────────────────────────────
```

### Step 10: Final Summary

```
✅ CVE WORKFLOW COMPLETE

📊 Results:
- Tickets Assigned: 10
- CVEs Fixed: 8
- CVEs Failed: 2 (logged with research)
- PRs Created: 8
- Jira Comments Added: 8

📁 Full log: docs/cves/logs/cve-resolution-log.md
📝 Slack message above - copy and send to team
```

---

## Mode: Fix Single CVE (`/fix-cve <TICKET-ID>`)

Execute Steps 6-10 for one ticket. Still fully autonomous.

---

## Mode: Status Check (`/fix-cve status`)

Query and display assigned CVEs. No modifications.

---

## Logging Failed CVEs

When a CVE cannot be fixed, **log the research**:

```markdown
#### CVE-YYYY-NNNNN (package)
- **Issue:** What went wrong
- **Research:** What was searched/investigated  
- **Attempted:** What fixes were tried
- **Result:** Why it failed
- **Recommendation:** Manual steps needed
```

---

## See Also

- [CVE Developer Guide](../../docs/cves/cve-developer-guide.md)
- [Python CVE Fixes](../../docs/cves/python.md)
- [Agents CVE Autofix](../../docs/cves/agents-cve-autofix.md)
