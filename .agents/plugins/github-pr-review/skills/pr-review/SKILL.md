---
name: pr-review
description: Review pull requests in the notebooks repository using GitHub MCP tools and the project review standards. Use when reviewing a PR, when the user asks for automated PR feedback, or when the workflow invokes Antigravity for GitHub review.
---

# PR Review

## Scope

Review the pull request for correctness, security, maintainability, and missing tests.
Use GitHub MCP tools for pull request data and review submission.

## Workflow

1. If a prepared `review-context.json` is present, use it first to focus the review.
2. Read the pull request metadata, file list, and diff with GitHub MCP.
3. Prioritize correctness and security issues before style or refactoring notes.
4. Leave inline comments only on changed lines when there is a real problem or a concrete improvement.
5. Submit the pending review as a `COMMENT` review with an empty body (inline comments only). Never approve and never request changes.
6. Output the overall summary in your final response only. CI upserts it as a single updating issue comment.

## Comment rules

- Only comment when you found a real issue or a concrete improvement.
- Keep each comment focused on one issue.
- Use severity emojis: `🔴` critical, `🟠` high, `🟡` medium, `🟢` low.
- Do not ask the author to "check", "confirm", or "verify" something.
- Do not explain what the code already does.
- Do not comment on unchanged lines.

## Summary format

When you finish the review, use this exact structure in your final response (not in the GitHub review body):

```markdown
## 📋 Review Summary

<2-3 sentence overview>

## 🔍 General Feedback

- <concise bullets that do not duplicate inline comments>
```

## Repo-specific guidance

- Prefer the smallest safe fix over broad refactors.
- Be careful with build and CI changes: multi-arch notebook builds fan out into many jobs, so call out regressions that would multiply across the matrix.
- When `review-context.json` contains capped excerpts or check runs, treat it as bounded evidence and avoid re-expanding into unrelated files unless the MCP diff still leaves a real ambiguity.
- Missing or weak tests are worth flagging when the diff changes non-trivial behavior.
- Avoid suggestions that would require broad unrelated cleanup.
