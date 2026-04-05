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
- `cypress/` is legacy. Do not modify it, install Cypress types, or integrate with Playwright.
- Fixture types live in `tests/fixtures.ts`. Fixture implementations live in each spec's `base.extend<T>()` call.
- `connectCDP` fixture switches between Playwright-managed browser and an external Chrome connected via CDP on a given port.
- OpenShift tests (`openshift_console.spec.ts`) require `KUBECONFIG` env var pointing to a valid kubeconfig.
