# AI Coding Assistant Project Configuration

Each AI coding tool has its own directory convention for project-specific instructions and skills. Teams using multiple tools need to understand the landscape to avoid duplication and keep conventions in sync.

This document captures the state of the field as of mid-2026, based on hands-on evaluation.

## Tool-by-Tool Reference

### Claude Code (Anthropic)

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `CLAUDE.md` | Always loaded at conversation start; hierarchical (root + parent dirs + `~/.claude/CLAUDE.md`) |
| Skills | `.claude/skills/<name>/SKILL.md` | Conditional activation via YAML frontmatter (`paths`, `disable-model-invocation`) |
| Slash commands | `.claude/commands/` | Legacy; skills are now the preferred mechanism |
| Custom subagents | `.claude/agents/<name>.md` | Define specialized agents with their own tool access and memory |

### Gemini CLI (Google)

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `GEMINI.md` | Equivalent to CLAUDE.md; hierarchical (root + parents + `~/.gemini/GEMINI.md`). Use `/memory show` to inspect, `/memory reload` to refresh |
| Skills | `.gemini/skills/` **and** `.agents/skills/` | Both natively supported. SKILL.md with metadata; optional `scripts/`, `resources/`, `assets/` subdirs |
| Config | `.gemini/settings.json` | Project-level configuration |

Gemini CLI skills are autonomously invoked by the model based on the task context, not triggered by user slash commands. Gemini CLI is notable for being one of the few tools that natively reads the `.agents/skills/` directory.

### OpenCode (open-source)

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `AGENTS.md` | Primary instructions file; **falls back to `CLAUDE.md`** if absent |
| Skills | `.opencode/skills/<name>/SKILL.md` | Native skills directory; falls back to `.claude/skills/` |
| Agents | `.opencode/agents/` | Agent definitions |
| Global config | `~/.config/opencode/` | User-level configuration |

OpenCode's fallback to `CLAUDE.md` and `.claude/skills/` means teams already using Claude Code get partial compatibility for free.

### Cursor

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Rules | `.cursor/rules/*.mdc` | Markdown with YAML frontmatter; `alwaysApply: true/false` controls conditional loading |

Cursor has no skills or agents directory convention.

### GitHub Copilot

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `.github/copilot-instructions.md` | Loaded as context for Copilot chat |

## Cross-Tool Sharing

The practical problem: your team has Jira conventions, coding standards, or workflow instructions that should be available regardless of which tool a developer uses. Here are the approaches we evaluated.

### Approach 1: Pointers (what we use)

Each tool's instructions file contains a one-line pointer to the canonical source.

```
# CLAUDE.md
## References
- Jira conventions: see `.cursor/rules/jira-conventions.mdc`
```

**Pros:** Simple, robust, no dependencies. Each tool loads only a few bytes of overhead.
**Cons:** Each tool still needs its own pointer file.

### Approach 2: Symlinks

Symlink one tool's directory to another (e.g., `.claude/skills/jira` -> `.cursor/rules/jira-conventions.mdc`).

**Pros:** Single source of truth.
**Cons:** Fragile across OS and git. Frontmatter formats differ between tools, so a file valid for one tool may not parse correctly in another.

### Approach 3: Vercel Labs `skills` CLI

The [`skills`](https://github.com/vercel-labs/skills) npm package (`npx skills add/list/remove`) is a package manager for AI agent skills. It downloads community-maintained SKILL.md files and copies them into each tool's expected directory.

```bash
npx skills add vercel/ai    # installs into .claude/skills/, .cursor/rules/, etc.
npx skills list              # shows installed skills
```

**Pros:** Community skill ecosystem; handles multi-tool sync automatically.
**Cons:** Third-party dependency. Despite claims of being a "universal standard," it acts as a sync utility — most tools do not natively monitor `.agents/skills/`. The exception is Gemini CLI, which does read `.agents/skills/` natively.

The project references a spec at [agentskills.io](https://agentskills.io). It is a Vercel Labs initiative, not an industry-ratified standard, though it has broad ambitions (claims support for 44+ agents).

## What We Did in This Repo

- Created `CLAUDE.md` at the repo root with a pointer to `.cursor/rules/jira-conventions.mdc`
- `.cursor/rules/jira-conventions.mdc` remains the single source of truth for Jira project IDs, custom fields, and MCP call patterns
- Both Cursor and Claude Code can access the same knowledge without content duplication

## Recommendations

1. **Keep instructions in one canonical file** and point other tools to it
2. **For simple project context**, use the tool's native instructions file (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`)
3. **For complex reusable workflows**, use the tool's skills directory (`.claude/skills/`, `.gemini/skills/`)
4. **For cross-tool teams**, the pointer approach is simplest; the Vercel Labs `skills` CLI is worth watching for community skills but adds a dependency
5. **Don't chase "universal standards"** — the field is still consolidating. Gemini CLI's native `.agents/skills/` support is a step toward convergence, but other tools haven't followed yet
