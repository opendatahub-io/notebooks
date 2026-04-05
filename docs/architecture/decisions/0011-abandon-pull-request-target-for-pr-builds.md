# 11. Abandon pull_request_target for PR builds

Date: 2026-04-05

## Status

Proposed

## Context

The repo uses `pull_request_target` in two PR workflows (`build-notebooks-pr-aipcc.yaml`,
`build-notebooks-pr-rhel.yaml`) to build RHOAI images from fork PRs. This trigger runs the
workflow from the base branch with full access to secrets, even when the PR comes from a fork.

### Problems with pull_request_target

1. **Security (PwnRequest):** The workflow checks out and builds fork code with access to
   RHEL subscription credentials, AIPCC registry credentials, and `GIT_CRYPT_KEY`. While an
   authorization gate (`getCollaboratorPermissionLevel`) restricts this to authorized
   collaborators, the attack surface exists. See RHAIENG-3913 audit, Trivy incident.

2. **"Main always applies":** `pull_request_target` runs the workflow YAML from the base
   branch (main), not from the PR branch. When the workflow definition changes on main,
   it breaks builds for release branches (`rhoai-3.3`, `rhoai-3.4`). This is a persistent
   maintenance burden — every main change must consider all active release branches.

3. **Complexity:** Two separate workflows (`pr-aipcc.yaml`, `pr-rhel.yaml`) duplicate the
   matrix generation, authorization gate, and build logic from `build-notebooks-pr.yaml`.

### Why pull_request_target was used

GitHub withholds secrets from fork PRs on `pull_request` trigger. The build needs RHEL
subscription entitlements and AIPCC registry credentials. `pull_request_target` provides
these secrets even for fork PRs.

### Key insight: same-repo PRs get secrets on pull_request

For PRs from branches in the same repo (not forks), `pull_request` trigger provides full
secret access. Since most contributors have write access and push branches to the main repo,
`pull_request_target` is unnecessary for the majority of PRs.

## Decision

### Move RHOAI builds to `build-notebooks-pr.yaml` using `pull_request` trigger

Add a `build-rhoai` job alongside the existing ODH `build` job:

- **`build-odh`**: Runs for all PRs (fork + same-repo). Uses ODH Dockerfiles. No subscription.
- **`build-rhoai`**: Runs for same-repo PRs only (fork check: `is_fork == 'false'`). Uses
  `subscription: true`, `konflux: true` for RHOAI Dockerfiles.

Fork PRs get ODH builds (no secrets needed) plus a guidance comment directing the
contributor to push their branch to the main repo for full RHOAI CI.

### Transition plan

1. **Phase 1 (this PR):** Add `build-rhoai` job to `build-notebooks-pr.yaml`. Modify
   `pr-aipcc.yaml` and `pr-rhel.yaml` to skip same-repo PRs (output `authorized: false`).
   Both old and new workflows coexist — old ones only fire for fork PRs.

2. **Phase 2 (future):** After confirming Phase 1 works for several sprints, delete
   `build-notebooks-pr-aipcc.yaml` and `build-notebooks-pr-rhel.yaml`. Fork PRs that need
   RHOAI builds will require a maintainer to cherry-pick to a same-repo branch.

### Concurrency groups

Use `github.event.pull_request.number` (not `github.head_ref`) in concurrency group keys.
`head_ref` is just the branch name without fork owner — two forks with the same branch name
would collide. PR number is unique per PR.

For non-PR events (push, workflow_dispatch), the fallback determines concurrency behavior:

- **`github.ref`**: Groups by branch — serializes pushes to the same branch (e.g., two rapid
  pushes to `main` queue instead of running in parallel). Simple and predictable.
- **`github.run_id`**: Unique per run — allows full parallelism. Risk: many concurrent runs
  on the same branch could waste runners.

We start with `github.ref` and will revisit based on practical experience.

For workflows triggered only by `pull_request` (e.g., `build-notebooks-pr.yaml`), the PR
number is always available and no fallback is needed:

```yaml
concurrency:
  group: ${{ format('{0}-{1}', github.workflow, github.event.pull_request.number) }}
  cancel-in-progress: true
```

For workflows triggered by both `push` and `pull_request`, add a fallback:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

### Push/PR deduplication

Workflows that trigger on both `push` and `pull_request` double-fire for same-repo branch
PRs. Fix: restrict `push` to protected branches only:

```yaml
on:
  push:
    branches: [main, stable, 'rhoai-*']
  pull_request:
```

## Consequences

- **Security improvement:** Same-repo RHOAI builds move from `pull_request_target` to
  `pull_request`, eliminating PwnRequest surface for the majority of PRs.
- **Simpler workflow structure:** One workflow handles both ODH and RHOAI builds instead
  of three separate workflows with duplicated logic.
- **"Main always applies" mitigated:** `pull_request` uses the PR branch's workflow
  definition, so release branch changes don't break when main changes.
- **Fork PR limitation:** Fork PRs only get ODH builds. RHOAI builds require same-repo
  branch. This is documented in CONTRIBUTING.md with clear guidance.
- **Runner cost:** Same-repo PRs now run both ODH and RHOAI builds (previously only ODH
  on odh-io). This doubles build cost per PR but catches RHOAI regressions earlier.

## References

- [RHAIENG-3913](https://redhat.atlassian.net/browse/RHAIENG-3913) — GHA hardening audit
- [RHAIENG-3914](https://redhat.atlassian.net/browse/RHAIENG-3914) — pull_request_target evaluation
- [RHAIENG-4290](https://redhat.atlassian.net/browse/RHAIENG-4290) — Fork PR CI monitoring
- ADR 0008 — GitHub Actions SHA pinning
- [GitHub Security Lab: Preventing pwn requests](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/)
- `workflow_run` pattern evaluated and rejected — container build IS the untrusted code
  execution that needs secrets, can't split into safe/privileged stages
