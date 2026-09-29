# Agents Guide

## Verify changes

After code changes, run both:

```bash
pnpm typecheck   # type errors (noUncheckedIndexedAccess is on)
pnpm lint        # eslint with type-aware rules + playwright plugin
```

## Conventions

- `noUncheckedIndexedAccess` is on — `array[0]` returns `T | undefined`. Handle with `if`, `??`, `.at(0)`, or `const [first] = array`. Do not silence with `!` unless there is a comment explaining why.
- `pnpm` only (not npm/yarn). CI uses `pnpm install --frozen-lockfile`.
- `package.json5` is the single source of truth for Playwright version — Dockerfile and CI derive from it.
- `DEFAULT_TEST_IMAGE` in `playwright.config.ts` is parsed by `.github/workflows/test-playwright-action.yaml` via grep. Keep it as a single-line string assignment. Do not rename the variable or split across lines.
- `DEFAULT_JUPYTER_TEST_IMAGE` in `playwright.config.ts` is the default consumed by `scripts/run-offline-browser.sh`; keep it as a single-line string assignment so the launcher can read it without installing the TypeScript toolchain.
- `cypress/` is legacy. Do not modify it, install Cypress types, or integrate with Playwright.
- Fixture types live in `tests/fixtures.ts`. Fixture implementations live in each spec's `base.extend<T>()` call.
- `connectCDP` fixture switches between Playwright-managed browser and an external Chrome connected via CDP on a given port.
- OpenShift tests (`openshift_console.spec.ts`) require `KUBECONFIG` env var pointing to a valid kubeconfig.

## Tags

Use the following tags already present in the browser suite:

| Tag | Meaning |
|---|---|
| `@checode` | Tests for the Che-Code editor. |
| `@codeserver` | Tests for the Code-Server workbench. |
| `@jupyter` | Tests for Jupyter or JupyterLab workbenches. |
| `@offline` | The test is written so it does not need internet access to pass, making it suitable for air-gapped (disconnected) clusters. |
| `@openshift` | Tests that require an OpenShift cluster or console. |
| `@smoke` | Minimal, high-priority validation that the component works. |
| `@tier1` | Core, high-priority functionality and common workflows. |
| `@tier2` | Broader positive coverage for less critical paths. |
| `@tier3` | Negative, destructive, edge-case, or recovery coverage. |

Feature-area tags such as `@jupyter`, `@codeserver`, `@checode`, `@openshift`,
and `@offline` are independent of the tier tags. A test may carry more than one
tier tag when it belongs in several quality gates.
