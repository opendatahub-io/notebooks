# AI Coding Assistant Project Configuration

Each AI coding tool has its own directory convention for project-specific instructions and skills. Teams using multiple tools need to understand the landscape to avoid duplication and keep conventions in sync.

This document captures the state of the field as of mid-2026, based on hands-on evaluation and fact-checking.

## Agent Skills: The Cross-Tool Standard

The [Agent Skills](https://agentskills.io) open standard, created by Anthropic (Dec 2025) and maintained at [github.com/agentskills/agentskills](https://github.com/agentskills/agentskills), defines a portable format for extending AI coding agents with specialized knowledge and workflows. Licensed under Apache 2.0 (code) and CC-BY-4.0 (docs).

A skill is a directory containing a `SKILL.md` file with YAML frontmatter (`name`, `description`) and markdown instructions, plus optional `scripts/`, `references/`, and `assets/` subdirectories.

Skills use **progressive disclosure** to manage context efficiently:

1. **Catalog** (~50-100 tokens/skill): At startup, agents load only `name` and `description` from each skill
2. **Instructions** (<5000 tokens recommended): Full `SKILL.md` body loaded when the skill is activated
3. **Resources** (as needed): Supporting files loaded on demand during execution

The spec recommends scanning both a **client-specific directory** and the **`.agents/skills/` convention** for cross-client interoperability:

| Scope | Path | Purpose |
|-------|------|---------|
| Project | `<project>/.<your-client>/skills/` | Tool's native location |
| Project | `<project>/.agents/skills/` | Cross-client sharing |
| User | `~/.<your-client>/skills/` | Tool's native location |
| User | `~/.agents/skills/` | Cross-client sharing |

**Adopters** (45+): Claude Code, Cursor, Gemini CLI, GitHub Copilot (+ VS Code), OpenAI Codex, JetBrains Kiro, JetBrains Junie, Roo Code, OpenCode, OpenHands, Goose, Spring AI, Databricks, Snowflake, Mistral Vibe, and others. Full list at [agentskills.io](https://agentskills.io).

The Vercel Labs [`skills`](https://github.com/vercel-labs/skills) CLI (`npx skills add/list/remove`) is a package manager that installs community-maintained skills into the appropriate directories for each tool.

## Tool-by-Tool Reference

### Claude Code (Anthropic)

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `CLAUDE.md` | Always loaded at conversation start; hierarchical (root + parent dirs + `~/.claude/CLAUDE.md`) |
| Skills | `.claude/skills/<name>/SKILL.md` and `.agents/skills/` | Conditional activation via YAML frontmatter (`paths`, `disable-model-invocation`); follows Agent Skills spec |
| Slash commands | `.claude/commands/` | Legacy; skills are now the preferred mechanism |
| Custom subagents | `.claude/agents/<name>.md` | Define specialized agents with their own tool access and memory |

### Gemini CLI (Google)

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `GEMINI.md` | Equivalent to CLAUDE.md; hierarchical (root + parents + `~/.gemini/GEMINI.md`). Use `/memory show` to inspect, `/memory reload` to refresh |
| Skills | `.gemini/skills/` and `.agents/skills/` | Both natively supported; follows Agent Skills spec |
| Config | `.gemini/settings.json` | Project-level configuration |

Skills are autonomously invoked by the model based on the task context, not triggered by user slash commands.

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
| Rules | `.cursor/rules/*.mdc` | Markdown with YAML frontmatter; four activation modes: `alwaysApply`, glob patterns, description-triggered, or manual (`@` mention) |
| Skills | `.agents/skills/` | Supports Agent Skills spec (listed on agentskills.io) |

### GitHub Copilot

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `.github/copilot-instructions.md` | Always loaded for workspace |
| Compatibility aliases | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `CODEX.md` | Recognized at repo root |
| Modular instructions | `.github/instructions/*.instructions.md` | Glob-pattern triggered via `applyTo` frontmatter |
| Skills | `.agents/skills/` | Supports Agent Skills spec |

### OpenAI Codex

| Mechanism | Path | Behavior |
|-----------|------|----------|
| Project instructions | `CODEX.md` | Loaded at repo root |
| Skills | `.agents/skills/` | Supports Agent Skills spec |
| Global config | `~/.codex/config.toml` | User-level configuration |

## Cross-Tool Sharing

The practical problem: your team has Jira conventions, coding standards, or workflow instructions that should be available regardless of which tool a developer uses. Here are the approaches we evaluated.

### Approach 1: Pointers (what we use)

Each tool's instructions file contains a one-line pointer to the canonical source.

```markdown
# CLAUDE.md
## References
- Jira conventions: see `.cursor/rules/jira-conventions.mdc`
```

**Pros:** Simple, robust, no dependencies. Each tool loads only a few bytes of overhead.
**Cons:** Each tool still needs its own pointer file.

### Approach 2: Agent Skills in `.agents/skills/`

Place skills in `.agents/skills/` where 45+ tools can discover them natively.

```text
.agents/skills/jira-reference/
    SKILL.md    # name + description frontmatter, then instructions
```

**Pros:** Write once, discovered by all compatible tools. Progressive disclosure keeps context small.
**Cons:** Not all tools parse `description` for conditional activation the same way.

### Approach 3: Symlinks

Symlink equivalent structures (e.g., `.claude/skills/jira-reference` -> `.agents/skills/jira-reference`).

**Pros:** Single source of truth.
**Cons:** Fragile across OS and git. Frontmatter formats differ between tools.

The [`dotagents`](https://github.com/iannuttall/dotagents) CLI automates this — it maintains `.agents/` as the source of truth and symlinks into each tool's expected directory (`.claude/skills/`, `.cursor/skills/`, etc.). Note: Sentry maintains a separate [`getsentry/dotagents`](https://github.com/getsentry/dotagents) that takes a different approach, declaring skills, MCP servers, and hooks in a single `agents.toml` file.

### Approach 4: Vercel Labs `skills` CLI

The [`skills`](https://github.com/vercel-labs/skills) npm package (`npx skills add/list/remove`) is a package manager for community-maintained Agent Skills. It downloads SKILL.md files and installs them into each tool's expected directory.

```bash
npx skills add vercel-labs/agent-skills    # installs into .claude/skills/, .agents/skills/, etc.
npx skills list              # shows installed skills
```

**Pros:** Community skill ecosystem; handles multi-tool sync automatically.
**Cons:** Third-party dependency; adds tooling complexity.

## What We Did in This Repo

- Created `CLAUDE.md` at the repo root with a pointer to `.cursor/rules/jira-conventions.mdc`
- `.cursor/rules/jira-conventions.mdc` remains the single source of truth for Jira project IDs, custom fields, and MCP call patterns
- Both Cursor and Claude Code can access the same knowledge without content duplication

## Recommendations

1. **Keep instructions in one canonical file** and point other tools to it
2. **For simple project context**, use the tool's native instructions file (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`)
3. **For complex reusable workflows**, use Agent Skills in `.agents/skills/` for cross-tool portability, or `.claude/skills/` for Claude-specific features
4. **For cross-tool teams**, adopt `.agents/skills/` — it's the closest thing to a universal standard, with 45+ tools supporting it
5. **For community skills**, use the Vercel Labs `skills` CLI or `dotagents` to manage installation and syncing
