---
description: Greet the user using their Jira account display name
---

# /hello

## Purpose

Smoke-test Claude Code commands and Jira MCP. Prints `Hello <account name>!` using the authenticated Jira user.

## Prerequisites

- Jira MCP configured locally — see [docs/claude-mcp.md](../../docs/claude-mcp.md)
- Claude Code CLI logged in (`claude login`) if using terminal `/hello`

## Implementation

1. Fetch the current user's name via Jira MCP (try in order):
   - `jira_get_user_profile` with `user_identifier: "me"` → use `displayName`
   - If that fails: `jira_search` with JQL `assignee = currentUser() ORDER BY updated DESC`, `limit: 1`, `fields: assignee` → use `assignee.displayName`
2. Print to the user:

```
Hello <display name>!
```

Read-only. No file writes.

## Error handling

- **401 / unauthorized:** Tell the user Jira MCP is not authenticated; show the expected greeting format once auth is fixed.
- **Profile empty:** Fall back to `name`, then email local-part before the `@`.
- **All lookups fail:** Print `Hello there!` and explain Jira could not be reached.

## Examples

```
/hello
→ Hello Adriana Theodorakopoulou!
```
