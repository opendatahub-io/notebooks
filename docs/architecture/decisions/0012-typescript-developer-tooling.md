# 12. TypeScript developer tooling for browser tests

Date: 2026-04-05

## Status

Accepted

## Context

The `tests/browser/` Playwright test suite has TypeScript with `strict: true` but
no linting, formatting, or static analysis beyond `tsc`. Two classes of bugs go
undetected:

1. **Dead code from type narrowing** — `value ?? throw` where the type guarantees
   non-null. `tsc` allows `??` on any type; it doesn't warn about redundant null
   checks.

2. **Missing `await` on Playwright assertions** — `expect(locator).toBeVisible()`
   without `await` silently passes. Playwright assertions return Promises; dropping
   `await` means the assertion never executes.

### Landscape (2026)

**Linters:**

| Tool | Type-aware rules | Playwright plugin | Native TS config | Speed |
|------|-----------------|-------------------|------------------|-------|
| ESLint 9 + typescript-eslint v8 | Yes (`no-unnecessary-condition`, `no-floating-promises`) | Yes (`eslint-plugin-playwright`) | Yes (`eslint.config.ts`) | Moderate |
| Biome 2.x | No (no type-aware analysis) | No | N/A | Very fast |
| oxlint | No (no type-aware analysis) | No | N/A | Very fast |

Biome and oxlint are significantly faster but cannot perform type-aware analysis
because they don't invoke the TypeScript compiler. The two bugs that prompted this
decision both require type information to detect. Biome tracks this as a known
limitation.

**Formatters:**

| Tool | Notes |
|------|-------|
| Prettier | De facto standard, slow, config conflicts with ESLint |
| Biome | Fast, good coverage, but adding a second tool just for formatting adds complexity |
| ESLint Stylistic | Formatting rules maintained by the ESLint community after ESLint deprecated its own |
| dprint | Fast Rust formatter, plugin-based |

For a small test project, a separate formatter adds marginal value over
`.editorconfig` (already project-wide). Formatting can be added later if needed.

**Playwright-specific linting:**

`eslint-plugin-playwright` provides rules tailored to Playwright tests:
- `no-standalone-expect` — `expect()` outside `test()`/`step()`
- `missing-playwright-await` — missing `await` on Playwright assertions
- `no-conditional-in-test` — discourages conditional logic in tests
- `no-force-option` — discourages `{ force: true }` click overrides

These are unavailable in Biome/oxlint.

**TypeScript strictness:**

`noUncheckedIndexedAccess` makes `array[0]` return `T | undefined` instead of `T`.
Catches real bugs where test code assumes arrays are non-empty. Not enabled by
`strict: true`; must be opted into separately.

## Decision

1. **ESLint 9** with flat config (`eslint.config.ts`) for linting.
2. **typescript-eslint v8** with `recommendedTypeChecked` preset for type-aware rules.
3. **eslint-plugin-playwright** with `flat/recommended` preset for Playwright rules.
4. **Enable `noUncheckedIndexedAccess`** in tsconfig.json.
5. **No separate formatter** — `.editorconfig` suffices for now.
6. **No Biome/oxlint** — they can't catch the bugs that motivated this change.

## Consequences

- ESLint with type-aware linting is slower (~5-10s on this small project). Acceptable
  for a test suite with 8 TypeScript files.
- Developers need ESLint IDE extension (built into IntelliJ, official extension for
  VS Code) for inline feedback.
- New Playwright assertions must use `await` — enforced by both
  `@typescript-eslint/no-floating-promises` and `playwright/missing-playwright-await`.
- Adding Biome for formatting later is straightforward and non-conflicting.
