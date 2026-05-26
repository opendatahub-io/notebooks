# 8. Harden GitHub Actions: pin SHA digests

Date: 2026-04-04

## Status

Proposed

## Context

The March 2026 Trivy supply chain attack ([GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23))
demonstrated that mutable Git tags on GitHub Actions are a high-value attack vector. An
attacker force-pushed 75 of 76 version tags in `aquasecurity/trivy-action`, turning trusted
tag references into credential-stealing malware. Any workflow referencing these by tag
silently ran an infostealer that dumped secrets from the GitHub Actions Runner.

Our repo was not directly affected — `trivy-action` was already SHA-pinned. However, an
audit ([RHAIENG-3913](https://redhat.atlassian.net/browse/RHAIENG-3913)) found that the
majority of our ~70 third-party action references across 31 workflow files use mutable tags
(`@v6`, `@v8`), making them vulnerable to the same class of attack.

### Pinning actions alone is not sufficient

An action pinned by SHA can still reference mutable dependencies internally:
- A GitHub Action that uses a Docker container image by tag (e.g., `docker://aquasec/trivy:0.68.2`)
  is only as trustworthy as that tag. Docker tags are mutable — they can be re-pushed, just
  like Git tags.
- Actions that download binaries via `curl | bash` or fetch installers from URLs are similarly
  exposed.

Full immutability requires pinning the entire dependency chain: action SHAs, Docker image
digests (`image@sha256:...`), and ideally checksummed binary downloads.

### Developer experience matters

SHA digests are opaque. `@de0fac2e4500dabe0009e67214ff5f5447ce83dd` tells a human nothing.
Without good tooling, SHA pinning becomes a maintenance burden that developers work around
rather than embrace. The approach must include:
- Human-readable version comments alongside SHAs
- Automated tools for pinning and updating
- CI enforcement that catches regressions before merge

### State of SHA pinning in opendatahub-io

An audit of the organization (April 2026) found:
- **opendatahub-io/opendatahub-operator** — most thorough: all actions SHA-pinned with version
  comments, done manually (no tooling).
- **opendatahub-io/models-as-a-service**, **opendatahub-io/ODH-Build-Config** — also SHA-pinned,
  likely copied from operator.
- **opendatahub-io/notebooks**, **opendatahub-io/odh-dashboard**, and most other repos — use
  mutable tag references exclusively.
- **No repo in the org uses pinact, ratchet, or any automated pinning tool.** Renovate/MintMaker
  is deployed for Tekton and Dockerfile updates, but `github-actions` is not in `enabledManagers`.
- In the broader Red Hat ecosystem (redhat-appstudio, konflux-ci), only one repo
  (`release-review-rot`) uses step-security/harden-runner. No pinact or ratchet adoption found.

## Decision

### Pin all GitHub Actions by full commit SHA with version comment

Use the format recognized by both Renovate and pinact:

```yaml
uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2
```

### Use `pinact` for local workflow and CI enforcement

[pinact](https://github.com/suzuki-shunsuke/pinact) (v3.9.0+) is a Go binary that:
- Resolves tag references to SHA + version comment (`pinact run`)
- Verifies existing pins match their claimed version (`pinact run --verify`)
- Detects unpinned actions in CI (`pinact run --check`, exits non-zero)
- Updates to latest versions (`pinact run --update`)
- Outputs SARIF for GitHub Code Scanning integration (`--format sarif`)

**Installation:** `brew install pinact` (macOS/Linux). Not available via npm; it is a Go
binary. `go install github.com/suzuki-shunsuke/pinact/v3/cmd/pinact@latest` works on any
platform with Go installed.

**Authentication:** pinact requires `GITHUB_TOKEN` for authenticated API access (avoids
rate limiting). In CI, use `${{ secrets.GITHUB_TOKEN }}`. Locally, `gh auth token` works.

**CI enforcement:** Add a `pinact run --check --verify` step to the code-quality workflow.
This catches both unpinned actions and tampered SHA-to-version mappings.

### Enable Renovate `github-actions` manager for automated updates

Add `"github-actions"` to `enabledManagers` in `.github/renovate.json5` so Renovate/MintMaker
automatically proposes PRs when new action versions are released — updating both the SHA and
the version comment. Without this, SHA pins would require manual maintenance.

```json5
"enabledManagers": [
    "tekton",
    "dockerfile",
    "custom.regex",
    "github-actions",  // NEW: auto-update SHA-pinned actions
],
```

### Supply chain audit of CI action runners

When evaluating GitHub Actions for CI use, we audited whether the actions themselves
"pin all the way down" — i.e., whether SHA-pinning the action ref is sufficient to
guarantee immutability of everything that executes.

**suzuki-shunsuke/pinact-action@v2.0.0 — pins all the way down:**

The action uses `runs: using: node24` with a bundled `dist/index.js` (compiled via ncc).
All NPM dependencies are frozen at build time inside the bundle — the SHA pin covers them.
At runtime, the action downloads three binaries, each with cryptographic verification:

1. **Aqua bootstrap (v2.55.1):** SHA-256 checksum hardcoded in the bundled JS per platform.
   Downloaded binary is verified before execution.
2. **Aqua self-update (v2.56.1):** Verified via SLSA provenance attestation
   (`multiple.intoto.jsonl`). This is stronger than checksum-only verification — it
   proves the binary was built by the official CI pipeline from the expected source.
3. **pinact (v3.9.0) and reviewdog (v0.21.0):** Installed via aqua with
   `checksum: { enabled: true, require_checksum: true }` in the bundled `aqua.yaml`.
   Aqua refuses to install if the SHA-256 checksum (from the committed
   `aqua-checksums.json`) doesn't match.

**jdx/mise-action@v4 — does NOT pin all the way down:**

The action also uses `runs: using: node24` with bundled JS, but has significant gaps:

1. **Version resolution:** By default (no `version` input), it fetches
   `https://mise.jdx.dev/VERSION` — a **mutable URL** returning the current latest version.
2. **Binary download:** Downloads from `mise.jdx.dev` or GitHub Releases with **no checksum
   verification by default**. The `sha256` input exists but is optional and empty by default.
3. **No signature/provenance verification:** No Cosign, SLSA, or sigstore checks of any kind.
4. **Mutable tag:** The `v4` tag is a moving major-version tag, not an immutable release.

To use mise-action safely, a caller would need to: (a) SHA-pin the action ref,
(b) specify a fixed `version` input, and (c) provide the `sha256` input. Most users
(and the official docs) do none of these.

### Future: pin Docker images by digest in workflows

Docker image references in workflow files (e.g., `docker.io/nginx`, `registry.access.redhat.com/ubi9/ubi`)
should be pinned by digest (`@sha256:...`). This is tracked in [RHAIENG-3913](https://redhat.atlassian.net/browse/RHAIENG-3913)
items 3 and 5, and is a separate effort from action SHA pinning.

## Consequences

- **Security:** Eliminates mutable-tag supply chain risk for GitHub Actions. The remaining
  attack surface (Docker images, curl|bash installers) is acknowledged and tracked separately.
- **Developer experience:** `pinact run` handles pinning locally. Renovate handles updates.
  CI enforces compliance. Developers never need to manually look up SHAs.
- **Maintenance:** Renovate PRs will be more frequent (one per action update instead of
  silent tag-following). Grouping all action updates into a single PR mitigates this.
- **Onboarding:** New contributors adding an action by tag will get a CI failure with a clear
  message pointing them to `pinact run`.

## Known limitations

- **Verification gaps:** `aquasecurity/trivy-action` cannot be verified by `pinact --verify`
  in CI because the `aquasecurity` org has a GitHub IP allowlist that blocks GHA runner IPs.
  This action is excluded via `--exclude '^aquasecurity/trivy-action$'`. If other actions
  from this org are added, they may need similar exclusion — verify manually first.

## References

- [RHAIENG-3913](https://redhat.atlassian.net/browse/RHAIENG-3913) — Harden GitHub Actions
  workflows against supply chain attacks (comprehensive audit)
- [Trivy supply chain attack advisory](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)
- [StepSecurity analysis](https://www.stepsecurity.io/blog/trivy-compromised-a-second-time---malicious-v0-69-4-release)
- [pinact](https://github.com/suzuki-shunsuke/pinact) — GitHub Actions SHA pinning tool
- [GitHub Security Lab: Preventing pwn requests](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/)