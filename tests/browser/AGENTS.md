# Agents Guide

## Verify changes

Always run `pnpm exec tsc --noEmit` after code changes to catch type errors.

## Conventions

- `pnpm` only (not npm/yarn). CI uses `pnpm install --frozen-lockfile`.
- `package.json5` is the single source of truth for Playwright version — Dockerfile and CI derive from it.
- `DEFAULT_TEST_IMAGE` in `playwright.config.ts` is parsed by `.github/workflows/test-playwright-action.yaml` via grep. Keep it as a single-line string assignment. Do not rename the variable or split across lines.
- `cypress/` is legacy. Do not modify it, install Cypress types, or integrate with Playwright.
- Fixture types live in `tests/fixtures.ts`. Fixture implementations live in each spec's `base.extend<T>()` call.
- `connectCDP` fixture switches between Playwright-managed browser and an external Chrome connected via CDP on a given port.
- OpenShift tests (`openshift_console.spec.ts`) require `KUBECONFIG` env var pointing to a valid kubeconfig.
