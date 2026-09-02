# 18. Run GitHub Actions workflows locally with act

Date: 2026-09-02

## Status

Proposed

## Context

Iterating on composite actions and workflows (e.g. the git-crypt-auth action in
PR [#4503](https://github.com/opendatahub-io/notebooks/pull/4503)) requires a fast
local loop: full CI round-trips are slow, and some behaviors cannot be verified in
CI at all — a job containing a failed step is always reported as a red check, so
negative-path logic can only be exercised locally.

[nektos/act](https://github.com/nektos/act) runs GitHub Actions workflows in local
containers. We validated it against the `test-git-crypt-auth.yaml` workflow
(2026-09-02, Apple Silicon, act v0.2.89 — the latest release, published 2026-06-01):
all four jobs run green.

Three blockers in this repo, and their resolutions:

### 1. act's schema validation rejects `code-quality.yaml`

act validates every workflow file it loads against a bundled JSON schema, and this
validation is **always on** — there is no flag, environment variable, or config to
skip it (both the default and `--strict` paths in `pkg/model/workflow.go` call the
same check; `--strict` only adds stricter checks). `code-quality.yaml` uses the
`code-quality: write` permission scope (required by `upload-code-coverage` and
accepted by GitHub's own runners), but act's schema predates that scope and fails:

```
Error: workflow is not valid. 'code-quality.yaml': ... Unknown Property code-quality
Actions YAML Schema Validation Error detected:
For more information, see: https://nektosact.com/usage/schema.html
```

Any bare `act` invocation parses every workflow under `.github/workflows/` and dies
on this file before doing anything. **Workaround: always target the workflow under
test with `-W`** — act only validates the files it loads.

### 2. The official platform images are abandoned

Our jobs run on `ubuntu-26.04` (self-hosted runner label), which act has no
built-in mapping for — a `-P` platform mapping is required. The image act's docs
point at, `nektos/act-environments-ubuntu`, has not been updated since February
2020 (per act's own `IMAGES.md`; Docker Hub retains only the 18.04 tags). We build
a one-line image from the same OS as the CI runners — native arm64 on Apple
Silicon, so no `--container-architecture` emulation is needed.

The image must **keep its apt package lists** (no `rm -rf /var/lib/apt/lists/*`):
the `apt-install` action passes `update: 'false'`, relying on the self-hosted
runners' pre-seeded index. On a bare distro image, `apt-get install git-crypt`
fails with `E: Unable to locate package`.

### 3. Secrets and fixture data

Workflow secrets (e.g. `GIT_CRYPT_KEY`) are supplied via `--secret-file`
(`KEY=value` lines, mode 600). A fully green run of the git-crypt workflow needs
the real key; without it, a scratch "fixture" repo with a synthetic git-crypt key
(git-crypt 0.8.0 layout: `.git/git-crypt/keys/default`, `filter=git-crypt` line in
`.gitattributes`) exercises everything except the real key↔blob pairing.

## Decision

Adopt the following local setup for running workflows with act:

1. **Always invoke act with `-W` targeting a specific workflow** (bare `act` is
   unusable in this repo while any workflow contains a schema-incompatible
   construct):

   ```bash
   act workflow_dispatch \
     -W .github/workflows/test-git-crypt-auth.yaml \
     -P ubuntu-26.04=act-ubuntu-2604 \
     --secret-file "$SECRETS_FILE" \
     --pull=false
   ```

   `workflow_dispatch` avoids `branches:`/`paths:` filters; `--pull=false` avoids
   registry lookups for the local image.

2. **A one-line local runner image** matching the CI runner OS:

   ```bash
   mkdir -p /tmp/actimg && cd /tmp/actimg
   printf 'FROM ubuntu:26.04\nRUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends sudo git python3\n' > Dockerfile
   docker build -t act-ubuntu-2604 .
   ```

   `sudo`, `git`, and `python3` are required by the `apt-install` action and the
   workflow's verification steps. The apt lists are intentionally **not** pruned
   (see Context §2). Rebuild the image when the runner OS changes, or when
   installs start failing against a stale list.

3. On approval of this ADR, **document the `-W` requirement in `.github/AGENTS.md`**
   so future agents and contributors do not re-discover the schema blocker.

### Upstream status: `code-quality` in act's schema

The `code-quality` permission rejection is an upstream schema gap, not a repo bug —
and a known one:

- [nektos/act#6119](https://github.com/nektos/act/pull/6119) (open) — "feat: add
  passive support for `code-quality` (and related) permissions": adds
  `code-quality`, `artifact-metadata`, and `vulnerability-alerts` to
  `pkg/schema/workflow_schema.json`. **Once this merges and ships, item 1 above
  (`-W`) becomes unnecessary.**
- The always-on validation is deliberate: [nektos/act#2414](https://github.com/nektos/act/issues/2414)
  (closed) — the schema should track GitHub's, and strictness is kept. The
  schema-lag pattern recurs in [#2766](https://github.com/nektos/act/issues/2766)
  (closed, `models: read`), [#2520](https://github.com/nektos/act/issues/2520) (open),
  [#2621](https://github.com/nektos/act/issues/2621) (open),
  [#6086](https://github.com/nektos/act/issues/6086) (open),
  [#6095](https://github.com/nektos/act/issues/6095) (open).
- The act fix pattern is a schema PR: [#6097](https://github.com/nektos/act/pull/6097)
  (merged, `concurrency.queue`) and [#6044](https://github.com/nektos/act/pull/6044)
  (merged, general schema update).
- No release newer than v0.2.89 exists as of 2026-09-02.

## Consequences

- Workflows and composite actions can be iterated locally in minutes; negative paths
  that cannot be expressed as green CI checks can be exercised directly (e.g. run
  the unlock step with a wrong git-crypt key and observe the trap-based cleanup).
- `-W` is a standing requirement until act ships the #6119 schema update; the cost
  is one flag.
- The local image is machine-local, not shared; the Dockerfile is one line.
- act is not a CI replica: it runs workflow logic in disposable containers on the
  dev machine — no org-level checks (Semgrep OSS, Konflux), no RHEL subscription /
  AIPCC registry access, no required-check semantics. It complements CI; the merge
  gate remains the PR's CI run.
- When a next act release including #6119 ships: re-verify, drop the `-W`
  workaround note, and flip this ADR to Accepted with the simplified flow.

## References

- [nektos/act](https://github.com/nektos/act) — run GitHub Actions locally
- [act schema docs](https://nektosact.com/usage/schema.html)
- [nektos/act#6119](https://github.com/nektos/act/pull/6119) — passive support for
  `code-quality` permissions (open)
- [opendatahub-io/notebooks#4503](https://github.com/opendatahub-io/notebooks/pull/4503)
  — git-crypt-auth composite action (motivating workflow)
- [ADR 0008](0008-harden-github-actions-pin-sha-digests.md) — SHA pinning of the
  `uses:` refs that local runs resolve
