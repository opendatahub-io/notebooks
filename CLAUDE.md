# Claude Code / Cursor AI Configuration

This file configures AI assistants (Claude Code, Cursor) for the Notebooks repository.

## Quick Start

1. **Copy MCP config templates:**
   ```bash
   # For Claude Code CLI
   cp .mcp.json.example .mcp.json
   
   # For Cursor IDE
   cp .cursor/mcp.json.example .cursor/mcp.json
   ```

2. **Set up credentials:**
   ```bash
   cp .env.mcp.local.example .env.mcp.local
   # Edit .env.mcp.local with your Jira email and API token
   ```

3. **Test the setup:**
   ```
   /hello
   ```

## References

| Resource | Description |
|----------|-------------|
| `.claude/commands/` | Slash commands (e.g., `/hello`, `/fix-cve`) |
| `.claude/skills/` | AI skills/playbooks (e.g., CVE resolution) |
| [docs/claude-mcp.md](docs/claude-mcp.md) | Full MCP setup guide |
| [AGENTS.md](AGENTS.md) | Repository agent guidelines |

## Available Commands

| Command | Description |
|---------|-------------|
| `/hello` | Smoke test — greets you via Jira MCP |
| `/fix-cve` | CVE resolution workflow |
| `/fix-cve plan` | Sprint planning — assign top CVEs |
| `/fix-cve <TICKET>` | Fix a specific CVE ticket |
| `/fix-cve status` | Show your assigned CVE tickets |

## Available Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| `cve-resolution` | "fix CVE", "CVE workflow" | Complete CVE resolution workflow |

## MCP Configuration

### Files

| File | Purpose | Secrets? |
|------|---------|----------|
| `.env.mcp.local` | Your Jira credentials | **Yes** (gitignored) |
| `.env.mcp.local.example` | Credential template | No |
| `.cursor/mcp.json` | Cursor MCP config | No (gitignored) |
| `.cursor/mcp.json.example` | Cursor config template | No |
| `.mcp.json` | Claude Code MCP config | No (gitignored) |
| `.mcp.json.example` | Claude Code config template | No |

### Jira MCP Tools

Once configured, these Jira tools are available:

- `searchJiraIssuesUsingJql` — Search tickets with JQL
- `getJiraIssue` — Get ticket details
- `editJiraIssue` — Update ticket fields
- `addCommentToJiraIssue` — Add comments
- `transitionJiraIssue` — Change ticket status

## Conventions

### Jira Projects

- **RHAIENG** — Upstream CVE trackers (the ones to fix)
- **RHOAIENG** — Per-image downstream trackers (auto-resolved)

### Commit Style

```
RHAIENG-XXXX: scope: description in imperative mood
```

Examples:
- `RHAIENG-1234: chore(deps): fix CVE-2026-12345 in requests`
- `RHAIENG-5678: fix(jupyter): resolve numpy version conflict`

### PR Format

```markdown
## Summary
- Brief description of change

## Jira
https://redhat.atlassian.net/browse/RHAIENG-XXXX

## Test Plan
- [ ] Tests pass
- [ ] CI passes
```

## Troubleshooting

### MCP Not Working

1. Verify `.env.mcp.local` exists and has valid credentials
2. Check that `.cursor/mcp.json` or `.mcp.json` exists
3. Restart Claude Code / Cursor
4. Test with `/hello`

### Jira Authentication Failed

1. Regenerate API token at: https://id.atlassian.com/manage-profile/security/api-tokens
2. Update `.env.mcp.local` with new token
3. Use your Atlassian email (not Red Hat SSO username)

## See Also

- [AGENTS.md](AGENTS.md) — General repository guidelines
- [docs/cves/cve-developer-guide.md](docs/cves/cve-developer-guide.md) — Full CVE workflow
- [CONTRIBUTING.md](CONTRIBUTING.md) — Development guidelines
