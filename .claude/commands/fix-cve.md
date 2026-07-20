---
description: Fix CVE vulnerabilities in the Notebooks repository
---

# /fix-cve - CVE Resolution Command

## Purpose

Guide the AI assistant through the complete CVE resolution workflow for the Notebooks repository. This command handles sprint planning, CVE triage, applying fixes, and logging results.

## Prerequisites

- Jira MCP configured locally — see [docs/claude-mcp.md](../../docs/claude-mcp.md)
- GitHub MCP configured for PR creation
- Access to the notebooks repository with write permissions
- Full guide: [docs/cves/cve-developer-guide.md](../../docs/cves/cve-developer-guide.md)

## Usage

```
/fix-cve                      # Interactive mode - shows menu
/fix-cve plan                 # Sprint planning - assign top CVEs
/fix-cve <TICKET-ID>          # Fix a specific CVE ticket
/fix-cve status               # Show status of assigned CVEs
```

## MANDATORY EXECUTION REQUIREMENTS

**⚠️ CRITICAL: This command specification MUST be followed exactly. NO shortcuts allowed.**

When executing this command, you MUST:

1. **Read the full CVE developer guide** at `docs/cves/cve-developer-guide.md` before proceeding
2. **Use Jira MCP** for all ticket operations (search, assign, update, comment)
3. **Follow the exact fix workflow** — constraints file → lockfile refresh → PR
4. **Log all actions** to `docs/cves/logs/cve-resolution-log.md`

## Execution Policy

**Permission Model:**
- **Read-only:** Jira queries, file reads, git status — execute without asking
- **Ask permission:** File modifications, git commits, PR creation, Jira status changes

---

## Mode: Interactive Menu

When `/fix-cve` is called without arguments, present this menu:

```
🔒 CVE Resolution Assistant

What would you like to do?

1. 📋 Sprint Planning - Fetch and assign top unassigned CVEs
2. 🔧 Fix a CVE - Enter a ticket ID to resolve
3. 📊 Status Check - View your assigned CVE tickets
4. 📖 Help - Show CVE resolution guide

Enter choice (1-4) or ticket ID:
```

---

## Mode: Sprint Planning (`/fix-cve plan`)

**Total Steps: 5**

### Step 1: Find Current Sprint

**Objective:** Identify the active Notebooks sprint

**Actions:**
```
Tool: searchJiraIssuesUsingJql
Parameters:
  - jql: project = RHAIENG AND component = Notebooks AND sprint in openSprints()
  - limit: 1
  - fields: ["customfield_10020"]
```

**Expected Output:**
```
✓ Current Sprint: Notebooks - [Sprint Name]
✓ Sprint ID: [ID]
```

### Step 2: Get Developer's Account ID

**Objective:** Identify the current user for ticket assignment

**Actions:**
```
Tool: atlassianUserInfo (or jira_get_user_profile)
```

**Expected Output:**
```
✓ User: [Display Name]
✓ Account ID: [ID]
✓ Email: [email]
```

### Step 3: Fetch Top 10 Unassigned CVEs

**Objective:** Find most urgent CVEs by due date

**Actions:**
```
Tool: searchJiraIssuesUsingJql
Parameters:
  - jql: |
      project = RHAIENG 
      AND component = Notebooks 
      AND labels IN (CVE) 
      AND type = Bug 
      AND status NOT IN (Closed, Resolved) 
      AND assignee IS EMPTY 
      AND duedate IS NOT EMPTY 
      ORDER BY duedate ASC
  - limit: 12
  - fields: ["key", "summary", "status", "duedate", "labels", "priority"]
```

**Expected Output:**
```
📋 Top Unassigned CVEs (by due date):

| # | Ticket | CVE | Package | Release | Due Date | Priority |
|---|--------|-----|---------|---------|----------|----------|
| 1 | RHAIENG-XXXX | CVE-YYYY-NNNNN | pkg | rhoai-X.Y | YYYY-MM-DD | Tier-N |
| ... |

Found X tickets. Would you like me to assign the top 10 to you?
```

### Step 4: Assign Tickets

**Objective:** Assign selected tickets to the developer and add to sprint

**Actions (for each ticket):**
```
Tool: editJiraIssue
Parameters:
  - issueIdOrKey: [ticket key]
  - updateFields:
      assignee: { accountId: "[user account id]" }
      customfield_10020: [sprint id]  # Sprint field
```

**Expected Output:**
```
✓ RHAIENG-XXXX assigned to you, added to sprint
✓ RHAIENG-YYYY assigned to you, added to sprint
...
✅ Assigned 10 tickets to [Name] for sprint [Sprint Name]
```

### Step 5: Log Sprint Planning

**Objective:** Record the planning session

**Actions:**
- Append to `docs/cves/logs/cve-resolution-log.md`

**Log Format:**
```markdown
## Session: [DATE] - Sprint Planning ([Sprint Name])

**Developer:** [Name] ([email])
**Sprint:** [Sprint Name] ([Date Range])
**Session Type:** Sprint Planning

### CVEs Assigned This Sprint

| CVE ID | Package | Tickets | Releases |
|--------|---------|---------|----------|
| CVE-YYYY-NNNNN | package | RHAIENG-XXXX | rhoai-X.Y |

### Outcome
- **Status:** planning_complete
- **Tickets Assigned:** 10
```

---

## Mode: Fix Specific CVE (`/fix-cve <TICKET-ID>`)

**Total Steps: 8**

### Step 1: Triage Ticket

**Objective:** Verify ticket type and gather details

**Actions:**
```
Tool: getJiraIssue
Parameters:
  - issueKey: [TICKET-ID]
  - fields: ["summary", "description", "status", "labels", "fixVersions", "customfield_*"]
```

**Validation:**
- If ticket is **RHOAIENG** (per-image tracker): 
  ```
  ⚠️ This is a per-image RHOAIENG tracker. 
  The fix should be via the parent RHAIENG tracker.
  Would you like me to find the parent tracker?
  ```
- If ticket is **RHAIENG**: Proceed with fix

**Expected Output:**
```
📋 Ticket Analysis:

Ticket: RHAIENG-XXXX
CVE: CVE-YYYY-NNNNN
Package: [package name]
Current Version: [version]
Fixed Version: [version] (if known)
Affected Releases: rhoai-2.25, rhoai-3.3, rhoai-3.4
Priority: Tier-[N]
Due Date: YYYY-MM-DD
```

### Step 2: Identify Fix Strategy

**Objective:** Determine how to fix the CVE

**Actions:**
1. Check if CVE is for Python or Node.js package
2. Read appropriate guide:
   - Python: `docs/cves/python.md`
   - Node.js: `docs/cves/nodejs.md`

**Expected Output:**
```
🔧 Fix Strategy:

Package Type: Python/Node.js
Fix Method: cve-constraints.txt / package.json
Target Branch: main (for all releases)
```

### Step 3: Create Fix Branch

**Objective:** Create a branch for the fix

**Actions:**
```bash
git fetch origin main
git checkout -b fix/cve-YYYY-NNNNN-[package] origin/main
```

**Expected Output:**
```
✓ Created branch: fix/cve-YYYY-NNNNN-[package]
```

### Step 4: Apply the Fix

**For Python CVEs:**

**Actions:**
1. Add constraint to `dependencies/cve-constraints.txt`:
   ```
   # CVE-YYYY-NNNNN: [brief description]
   package>=fixed.version
   ```

2. Regenerate lockfiles:
   ```bash
   make refresh-lock-files
   ```

**For Node.js CVEs:**

**Actions:**
1. Update `package.json` in affected directories
2. Run `npm install` to update lockfiles

**Expected Output:**
```
✓ Added constraint: package>=X.Y.Z
✓ Regenerated lockfiles
✓ Changed files:
  - dependencies/cve-constraints.txt
  - jupyter/minimal/ubi9-python-3.12/requirements.cpu.txt
  - [other affected files]
```

### Step 5: Run Tests

**Objective:** Verify the fix doesn't break anything

**Actions:**
```bash
make test-unit
```

**Expected Output:**
```
✓ Unit tests passed
```

### Step 6: Commit Changes

**Objective:** Create a properly formatted commit

**Actions:**
```bash
git add .
git commit -m "RHAIENG-XXXX: chore(deps): fix CVE-YYYY-NNNNN in [package]

Bump [package] to [version] to address CVE-YYYY-NNNNN.

[Brief description of the vulnerability]"
```

### Step 7: Create Pull Request

**Objective:** Submit the fix for review

**Actions:**
```bash
git push -u origin fix/cve-YYYY-NNNNN-[package]
gh pr create --title "RHAIENG-XXXX: chore(deps): fix CVE-YYYY-NNNNN in [package]" \
  --body "## Summary
- Fixes CVE-YYYY-NNNNN by bumping [package] to [version]
- Jira: https://redhat.atlassian.net/browse/RHAIENG-XXXX

## Test Plan
- [ ] Lockfiles regenerated
- [ ] Unit tests pass
- [ ] CI passes"
```

**Expected Output:**
```
✓ PR created: https://github.com/opendatahub-io/notebooks/pull/XXXX
```

### Step 8: Update Jira

**Objective:** Link PR and update ticket status

**Actions:**
```
Tool: addCommentToJiraIssue
Parameters:
  - issueIdOrKey: RHAIENG-XXXX
  - commentBody: |
      PR created: [PR URL]
      
      Fix: Bumped [package] to [version] via cve-constraints.txt
      
      Waiting for CI and review.

Tool: transitionJiraIssue (if available)
Parameters:
  - issueIdOrKey: RHAIENG-XXXX
  - transitionId: [In Review transition ID]
```

**Expected Output:**
```
✅ CVE Fix Complete!

Ticket: RHAIENG-XXXX
PR: https://github.com/opendatahub-io/notebooks/pull/XXXX
Status: In Review

Next Steps:
1. Wait for CI to pass
2. Get PR reviewed and merged
3. Ticket will auto-close when PR merges
```

---

## Mode: Status Check (`/fix-cve status`)

**Actions:**
```
Tool: searchJiraIssuesUsingJql
Parameters:
  - jql: |
      project = RHAIENG 
      AND component = Notebooks 
      AND labels IN (CVE) 
      AND assignee = currentUser()
      AND status NOT IN (Closed, Resolved)
      ORDER BY duedate ASC
  - fields: ["key", "summary", "status", "duedate", "priority"]
```

**Expected Output:**
```
📊 Your Assigned CVEs:

| Ticket | CVE | Status | Due Date | Priority |
|--------|-----|--------|----------|----------|
| RHAIENG-XXXX | CVE-YYYY-NNNNN | In Progress | YYYY-MM-DD | Tier-1 |
| ... |

Total: X tickets
Overdue: Y tickets ⚠️
```

---

## Error Handling

### Error: Jira MCP Not Configured

**Symptom:** Tool calls fail with authentication errors

**Solution:**
1. Check `docs/claude-mcp.md` for setup instructions
2. Verify `.env.mcp.local` contains valid credentials
3. Restart Claude Code / Cursor

### Error: Package Not in Lockfiles

**Symptom:** Constraint added but package not updated

**Solution:**
1. Check if package is a transitive dependency
2. May need to update the parent package instead
3. Check `pyproject.toml` for version pins

### Error: Make Command Fails

**Symptom:** `make refresh-lock-files` fails

**Solution:**
1. Ensure `uv` is installed: `pip install uv`
2. Check Python version: requires 3.14+
3. Run `uv sync --locked` first

---

## See Also

- [CVE Developer Guide](../../docs/cves/cve-developer-guide.md) - Full documentation
- [Python CVE Fixes](../../docs/cves/python.md) - Python-specific guidance
- [Node.js CVE Fixes](../../docs/cves/nodejs.md) - Node.js-specific guidance
- `/hello` - Test Jira MCP connection
