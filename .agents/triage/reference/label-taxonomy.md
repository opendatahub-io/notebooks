# Label Taxonomy

Labels used to track AI bug bash triage and execution outcomes in Jira (project RHAIENG for Notebooks bugs; see workflow docs for CVE trackers).

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

## Execution Phase Labels (outcomes)

Applied during or after AI fix attempts. For a given fix workflow, apply **exactly one** of the pre-merge execution outcomes below when the attempt concludes (success or failure). Definitions match the [AI First Bug Bash](https://docs.google.com/document/d/1aLED1gER-YINBjCHp5mUg5ChQf4BNpdRlnoEBKs_RF8/edit) outcome table.

### Success (mutually exclusive — pick one)

| Label | When to Apply |
|-------|---------------|
| `ai-fully-automated` | The bug was fixed and verified using **only** AI tools — tests and checks passed on the **first** run through the verify step with **no** prior test-failure cycle in that workflow. |
| `ai-accelerated-fix` | The bug was fixed and verified using AI tools **after more than one attempt** (e.g. at least one test-failure cycle before all checks passed). |

### Failure or post-merge

| Label | When to Apply |
|-------|---------------|
| `ai-could-not-fix` | AI attempted a fix but failed to produce a viable solution or found it too complex. |
| `ai-verification-failed` | AI generated a fix, but its own automated tests or regression checks failed (including after max retries / circuit breaker before merge). |
| `regressions-found` | Added **after merge** when a fix introduces a new defect elsewhere. **Never** applied before merge — if problems surface pre-merge, use `ai-verification-failed`. Counted in event metrics if added by April 2. |

`regressions-found` is **orthogonal** to the pre-merge set: it can be added later on top of an issue that already had `ai-fully-automated` or `ai-accelerated-fix`.

Do **not** use `ai-passed` as a Jira label — it appears only as survey wording in program materials, not as an outcome label in the table.

## Additional Labels

| Label | When to Apply |
|-------|---------------|
| `ai-retriage` | Bug needs re-assessment (e.g., initial verdict was wrong, new information available). |
| `ai-initiallymarkedfixable` | Tracks that the bug was initially marked `ai-fixable` but later changed to `ai-nonfixable` after deeper analysis. |

## Label Application Order

1. Triage: `ai-triaged` first, then verdict (`ai-fixable` or `ai-nonfixable`)
2. Fix attempt (pre-merge): exactly one of `ai-fully-automated`, `ai-accelerated-fix`, `ai-could-not-fix`, or `ai-verification-failed`
3. Post-merge monitoring: `regressions-found` if applicable (in addition to the prior outcome)

## Dashboard

The [bug bash dashboard](https://redhat.atlassian.net/jira/dashboards/24328) tracks these labels.
No label = no credit. Every triaged bug needs both the triage label and the outcome.
