# Claude MCP Setup Guide

This guide explains how to set up Model Context Protocol (MCP) for Claude Code and Cursor IDE to enable Jira integration.

## What is MCP?

MCP (Model Context Protocol) allows AI assistants to interact with external tools and services. In this repository, we use MCP to connect Claude/Cursor with Jira for CVE ticket management.

## Prerequisites

- Node.js 18+ installed
- Jira account with API token
- Claude Code CLI or Cursor IDE

## Quick Setup

### Step 1: Create Credential File

```bash
cp .env.mcp.local.example .env.mcp.local
```

Edit `.env.mcp.local`:
```bash
JIRA_EMAIL=your.email@redhat.com
JIRA_API_TOKEN=your-api-token-here
JIRA_URL=https://redhat.atlassian.net
```

### Step 2: Get Jira API Token

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a label (e.g., "Claude MCP")
4. Copy the token and paste into `.env.mcp.local`

### Step 3: Configure MCP

**For Cursor IDE:**
```bash
cp .cursor/mcp.json.example .cursor/mcp.json
```

**For Claude Code CLI:**
```bash
cp .mcp.json.example .mcp.json
```

### Step 4: Verify Setup

Test the connection:
```
/hello
```

Expected output:
```
Hello [Your Name]!
```

## Configuration Files

| File | Purpose | Committed? |
|------|---------|------------|
| `.env.mcp.local` | Your credentials | **No** (gitignored) |
| `.env.mcp.local.example` | Template | Yes |
| `.cursor/mcp.json` | Cursor config | **No** (gitignored) |
| `.cursor/mcp.json.example` | Template | Yes |
| `.mcp.json` | Claude Code config | **No** (gitignored) |
| `.mcp.json.example` | Template | Yes |

## Available Jira Tools

Once MCP is configured, these tools become available:

### searchJiraIssuesUsingJql

Search for tickets using JQL:
```
Tool: searchJiraIssuesUsingJql
Parameters:
  - jql: "project = RHAIENG AND labels = CVE"
  - limit: 10
  - fields: ["key", "summary", "status"]
```

### getJiraIssue

Get details of a specific ticket:
```
Tool: getJiraIssue
Parameters:
  - issueKey: "RHAIENG-1234"
```

### editJiraIssue

Update ticket fields:
```
Tool: editJiraIssue
Parameters:
  - issueIdOrKey: "RHAIENG-1234"
  - updateFields:
      assignee: { accountId: "..." }
```

### addCommentToJiraIssue

Add a comment:
```
Tool: addCommentToJiraIssue
Parameters:
  - issueIdOrKey: "RHAIENG-1234"
  - commentBody: "PR created: https://..."
```

### transitionJiraIssue

Change ticket status:
```
Tool: transitionJiraIssue
Parameters:
  - issueIdOrKey: "RHAIENG-1234"
  - transitionId: "31"  # e.g., "In Review"
```

## Troubleshooting

### "Unauthorized" Error

**Cause:** Invalid credentials

**Solution:**
1. Verify email in `.env.mcp.local` matches your Atlassian account
2. Regenerate API token if expired
3. Ensure token has no extra whitespace

### "Server not found" Error

**Cause:** MCP server not installed

**Solution:**
```bash
npm install -g @anthropic/mcp-atlassian
```

Or let npx install it automatically (may take a moment on first use).

### MCP Tools Not Appearing

**Cause:** Config file not loaded

**Solution:**
1. Ensure config file is in the correct location
2. Restart Claude Code / Cursor
3. Check file permissions

### Rate Limiting

**Cause:** Too many API calls

**Solution:**
- Jira has rate limits; wait a moment and retry
- Use `limit` parameter in searches to reduce calls

## Security Notes

1. **Never commit credentials** — `.env.mcp.local` is gitignored
2. **Use API tokens, not passwords** — Tokens can be revoked
3. **Rotate tokens regularly** — Regenerate if compromised
4. **Don't share tokens** — Each developer needs their own

## Advanced Configuration

### Multiple Jira Instances

If you need to connect to multiple Jira instances, create separate server entries:

```json
{
  "mcpServers": {
    "redhat-jira": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-atlassian"],
      "env": {
        "JIRA_EMAIL": "${env:JIRA_EMAIL}",
        "JIRA_API_TOKEN": "${env:JIRA_API_TOKEN}",
        "JIRA_URL": "https://redhat.atlassian.net"
      }
    },
    "other-jira": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-atlassian"],
      "env": {
        "JIRA_EMAIL": "${env:OTHER_JIRA_EMAIL}",
        "JIRA_API_TOKEN": "${env:OTHER_JIRA_TOKEN}",
        "JIRA_URL": "https://other.atlassian.net"
      }
    }
  }
}
```

### Adding GitHub MCP

To also enable GitHub integration:

```json
{
  "mcpServers": {
    "atlassian": { ... },
    "github": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-github"],
      "env": {
        "GITHUB_TOKEN": "${env:GITHUB_TOKEN}"
      }
    }
  }
}
```

## See Also

- [CLAUDE.md](../CLAUDE.md) — Quick reference for Claude configuration
- [CVE Developer Guide](cves/cve-developer-guide.md) — CVE resolution workflow
- [Atlassian MCP Documentation](https://github.com/anthropics/mcp-atlassian)
