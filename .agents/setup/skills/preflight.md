# Skill: Preflight Check

Walk through the prerequisites checklist interactively, verifying each tool is accessible.

## Procedure

Run each check and report pass/fail. See `prerequisites.md` (parent directory) for full details.

### Non-Negotiable Checks (stop if any fail)

1. **Jira access**: call `mcp__atlassian__getAccessibleAtlassianResources`. Look for cloud ID for `redhat.atlassian.net`. If missing, report: "Atlassian MCP not configured. Check your MCP server settings."

2. **Jira read**: call `mcp__atlassian__getJiraIssue` with `cloudId=<from step 1>` and `issueIdOrKey=RHAIENG-3712` (a known issue). If it returns data, pass. If error, report the error.

3. **Jira write**: ask the user "Shall I post a test comment to a Jira issue to verify write access? If yes, which issue key?" If user provides one, post a comment: `[Preflight test] Agent write access confirmed - {date}. This comment can be deleted.` If user declines, mark as SKIP.

4. **Local repo**: check that `AGENTS.md` exists in the current working directory. Run `git remote -v` and verify it points to `opendatahub-io/notebooks`. If not, report: "Not in the notebooks repo root."

### Strongly Recommended Checks

5. **GitHub CLI**: run `gh auth status`. Pass if authenticated.

6. **Python/uv**: run `python3 --version` (expect 3.14+) and `./uv --version`. Report versions.

7. **Build system**: run `which gmake 2>/dev/null || which make`. Pass if found.

8. **Container runtime**: run `podman --version` or `docker --version`. Pass if found.

9. **Registry auth**: run `podman login --get-login registry.redhat.io 2>&1`. Pass if returns a username.
   If not authenticated, report: "Run `podman login registry.redhat.io` with credentials from
   https://console.redhat.com/openshift/install/pull-secret"

10. **Red Hat VPN**: run `curl -sI https://gitlab.cee.redhat.com 2>&1 | head -1`. Pass if HTTP 200 or 302. Required for manifestbox SBOM downloads (CVE triage). If not connected, report: "Red Hat VPN not detected — manifestbox access unavailable. Connect to VPN if CVE triage is planned."

11. **Remote machine** (ask user): "Do you have SSH access to a remote machine with podman?
    If yes, image pulls and container tests can run there to avoid slow local transfers.
    Provide the SSH target (e.g., user@host) or skip."
    Record the answer for use by bugfix/triage skills.

### Optional Checks (report but don't block)

12. **Slack MCP**: call `mcp__slack-mcp-local__search_messages` with `query="test" count=1`. Pass if returns results.

13. **Web search**: call `WebSearch` with `query="opendatahub notebooks"`. Pass if returns results.

14. **GitLab CLI**: run `glab auth status`. If not authenticated, remind: "Visit https://red.ht/GitLabSSO to authenticate, then run `glab auth login`."

15. **Cluster access**: run `oc whoami`. Pass if returns a username.

16. **Google Docs**: run `which gws`. Pass if found. For reading docs programmatically, see `skills/google-doc.md`.

17. **Red Hat Cases API**: check if `docs/access_redhat_cases_api.md` exists. Report availability.

### Report Results

Print a summary table:
```
Preflight Results
-----------------
[PASS] Jira access (cloud ID: 2b9e35e3-...)
[PASS] Jira read (RHAIENG-3712 loaded)
[SKIP] Jira write (user declined test)
[PASS] Local repo (opendatahub-io/notebooks)
[PASS] GitHub CLI (authenticated as jdanek)
[PASS] Python 3.14.1 / uv 0.7.x
[PASS] gmake
[PASS] podman 5.x.x
[PASS] registry.redhat.io (logged in as jdanek)
[INFO] Remote machine: user@gpu-box.example.com (will use for image ops)
[SKIP] Slack MCP (not configured)
[PASS] Web search
[SKIP] GitLab CLI (visit https://red.ht/GitLabSSO)
[SKIP] Cluster access (oc not found)
[PASS] Google Docs (gws)
[PASS] Red Hat Cases API (docs available)

Ready to proceed. Suggested next steps:
- /triage-run — triage backlog bugs
- /triage-assess RHAIENG-XXXX — assess a specific bug
- /fix-start RHAIENG-XXXX — fix a specific ai-fixable bug
```

If any non-negotiable check failed, print setup instructions and stop.
