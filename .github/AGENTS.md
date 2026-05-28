# AI Agents Guide for GitHub Actions

This guide applies when modifying files under `.github/workflows/` or `.github/actions/`.

## SHA pinning requirement

All third-party GitHub Action references must use full commit SHAs with a version comment:

```yaml
uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6.0.2
```

**Never use mutable tags** like `@v6` or `@main`. See ADR 0008 for rationale (Trivy supply
chain attack, RHAIENG-3913 audit).

## Pinning workflow

After adding or changing any `uses:` line:

```bash
# Pin all actions to SHAs (requires GitHub token for API calls)
GITHUB_TOKEN=$(gh auth token) pinact run

# Verify everything is pinned and SHAs match version comments
GITHUB_TOKEN=$(gh auth token) pinact run --check --verify
```

Install pinact: `brew install pinact` (macOS/Linux) or
`go install github.com/suzuki-shunsuke/pinact/v3/cmd/pinact@v3.9.0`.

## Comment spacing

Use **two spaces** before `#` in version comments (yamllint `comments` rule):

```yaml
# Correct (two spaces before #)
uses: actions/checkout@de0fac2e...  # v6.0.2

# Wrong (one space before #)
uses: actions/checkout@de0fac2e... # v6.0.2
```

The `.pinact.yaml` at repo root configures this automatically.

## Automated updates

Renovate/MintMaker is configured (`enabledManagers` includes `github-actions`) to
automatically propose SHA pin updates when new action versions are released.

## Actions without major tags

Some actions only publish exact version tags (no `v8` major tag, only `v8.0.0`):
- `astral-sh/setup-uv` — use `@v8.0.0`, not `@v8`
- `actions/add-to-project` — use `@v1.0.2`, not `@v1`

Renovate has package rules to track these correctly.