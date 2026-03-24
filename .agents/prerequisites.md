# Prerequisites & Preflight Checklist

Run `/setup-preflight` to have the agent walk through these checks interactively.
Or verify manually using the commands below.

## Non-Negotiable (workflows fail without these)

### 1. Jira Access

**Tool**: Atlassian MCP

```
mcp__atlassian__getAccessibleAtlassianResources
```
Expected: returns cloud ID for `redhat.atlassian.net`

### 2. Jira Read

**Tool**: Atlassian MCP

Test with a known issue:
```
mcp__atlassian__getJiraIssue  cloudId=<cloud-id>  issueKey=RHAIENG-3712
```
Expected: returns issue details

### 3. Jira Write

**Tool**: Atlassian MCP

Dry-run on a test issue (confirm with user first):
```
mcp__atlassian__addCommentToJiraIssue  cloudId=<cloud-id>  issueKey=<test-issue>
  comment="[Preflight test] Agent write access confirmed. This comment can be deleted."
```
Expected: comment appears on the issue

### 4. Local Repo

**Tool**: filesystem

```bash
test -f AGENTS.md && echo "PASS" || echo "FAIL: not in notebooks repo root"
git remote -v | grep opendatahub-io/notebooks
```

## Strongly Recommended

### 5. GitHub CLI

```bash
gh auth status
```
Expected: authenticated to github.com

### 6. Python / uv

```bash
python3 --version   # expect 3.14+
./uv --version
```

### 7. Build System

```bash
which gmake 2>/dev/null || which make
```

## Optional (report available/unavailable, don't block)

### 8. Slack MCP

```
mcp__slack-mcp-local__search_messages  query="test"  count=1
```

### 9. Web Search

```
WebSearch  query="opendatahub notebooks"
```

### 10. GitLab CLI (for AIPCC base images)

```bash
glab auth status
```

If not authenticated: visit https://red.ht/GitLabSSO to auth, then `glab auth login`.
AIPCC base images repo: `gitlab.com/redhat/rhel-ai/core/base-images/app`

### 11. Cluster Access

```bash
oc whoami
oc get notebooks -A 2>/dev/null | head -5
```

### 12. Google Docs

```bash
gws docs documents get --params '{"documentId": "test"}' 2>&1 | head -1
```

### 13. Red Hat Cases Portal

See `docs/access_redhat_cases_api.md` for Hydra REST API setup.
Useful when a Jira issue references a customer support case.

## Preflight Summary Format

After checking, report results as:

```
Preflight Results
-----------------
[PASS] Jira access
[PASS] Jira read (RHAIENG-3712)
[PASS] Jira write (test comment posted)
[PASS] Local repo
[PASS] GitHub CLI
[PASS] Python 3.14.x / uv 0.x.x
[PASS] make (gmake)
[SKIP] Slack MCP (not configured)
[PASS] Web search
[SKIP] GitLab CLI
[SKIP] Cluster access
[SKIP] Google Docs
[SKIP] Red Hat Cases

Ready to proceed. Run /triage-run or /fix-start RHAIENG-XXXX
```
