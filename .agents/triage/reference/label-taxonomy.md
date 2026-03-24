# Label Taxonomy

Labels used to track AI bug bash triage and execution outcomes in Jira (project RHOAIENG).

## Triage Phase Labels

Applied during AI triage of bugs. Every triaged bug must have `ai-triaged` plus exactly one verdict.

| Label | When to Apply |
|-------|---------------|
| `ai-triaged` | On every bug processed by AI triage. Always applied first. |
| `ai-fixable` | AI determined this bug can be fixed without human coding. Clear reproduction path, fix is in agent-modifiable files, no cluster/GPU/browser access needed. |
| `ai-nonfixable` | AI determined this bug cannot be fixed autonomously. Requires cluster access, manual testing, upstream changes, architectural decisions, or insufficient information. |

Rules:
- `ai-fixable` and `ai-nonfixable` are **mutually exclusive** — never apply both.
- When uncertain, default to `ai-nonfixable` (conservative).
- A bug can be retriaged later — add `ai-retriage` and update the verdict label.

## Execution Phase Labels

Applied during or after AI fix attempts. Exactly one execution label per issue that was attempted.

| Label | When to Apply |
|-------|---------------|
| `ai-fully-automated` | AI fixed it, tests passed, human approved the PR. The complete success path. |
| `ai-could-not-fix` | AI attempted a fix but failed to produce a viable solution, or the issue was too complex. |
| `ai-verification-failed` | AI generated a fix, but its own automated tests or regression checks failed (after max retry attempts). |
| `regressions-found` | Applied **after merge** when a fix introduces a new defect elsewhere. Never applied before merge — if tests fail before merge, that's `ai-verification-failed`. Counted in event metrics if added by April 2. |

## Additional Labels

| Label | When to Apply |
|-------|---------------|
| `ai-retriage` | Bug needs re-assessment (e.g., initial verdict was wrong, new information available). |
| `ai-initiallymarkedfixable` | Tracks that the bug was initially marked `ai-fixable` but later changed to `ai-nonfixable` after deeper analysis. |

## Label Application Order

1. Triage: `ai-triaged` first, then verdict (`ai-fixable` or `ai-nonfixable`)
2. Fix attempt: execution label (`ai-fully-automated`, `ai-could-not-fix`, or `ai-verification-failed`)
3. Post-merge monitoring: `regressions-found` if applicable

## Dashboard

The [bug bash dashboard](https://redhat.atlassian.net/jira/dashboards/24328) tracks these labels.
No label = no credit. Every triaged bug needs both the triage label and the outcome.
