The `cypress/` directory holds Cypress tests and the `tests/` directory holds Playwright tests.

The following upstream projects have Playwright tests

* JupyterLab (https://github.com/jupyterlab/jupyterlab/tree/main/galata)
* code-server (https://github.com/coder/code-server/tree/main/test)

Honorable mentions include

* VSCode uses custom framework where Playwright is one of the possible runners (https://github.com/microsoft/vscode/wiki/Writing-Tests)
* RStudio components have Playwright tests (https://github.com/rstudio/shinyuieditor, https://github.com/rstudio/xterm.js)
* Some RStudio tests are implemented in private repository https://github.com/rstudio/rstudio/issues/10400, possibly in R https://github.com/rstudio/rstudio/tree/main/src/cpp/tests/automation with https://github.com/rstudio/chromote)

The following upstream projects have Cypress tests

* Elyra (https://github.com/elyra-ai/elyra/tree/main/cypress)
* ODH Dashboard (https://github.com/opendatahub-io/odh-dashboard/tree/main/frontend/src/__tests__/cypress)

# Cypress

The Cypress part was added after the Playwright part below.
Therefore, we are starting with an existing pnpm project folder.

```shell
pnpm add --save-dev cypress
pnpm cypress open
```

## Getting started

> https://learn.cypress.io/testing-your-first-application/installing-cypress-and-writing-your-first-test

Cypress operates in two modes,
the noninteractive `run` mode and the interactive `open` mode that is useful for development.

```shell
pnpm cypress run
pnpm cypress open
```

The `open` mode can be further enhanced by enabling the (currently experimental) Cypress Studio.
https://docs.cypress.io/app/guides/cypress-studio

```typescript
// cypress.config.ts
import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    experimentalStudio: true,
  },
})
```

## Execution model

Cypress execution model can be tricky.

Do read the introductory docs page, then the retry-ability,
and then the conditional testing page to appreciate the ramifications.

* https://docs.cypress.io/app/core-concepts/introduction-to-cypress
* https://docs.cypress.io/app/core-concepts/retry-ability
* https://docs.cypress.io/app/guides/conditional-testing

Cypress is not a general purpose web browser automation framework,
that was sufficiently clarified in the introduction docs, and also read the following.

* https://docs.cypress.io/app/references/trade-offs
* https://docs.cypress.io/app/guides/cross-origin-testing

Also do check out:

* https://docs.cypress.io/app/core-concepts/best-practices

# Playwright

This is a basic Playwright in Typescript that was setup like this

```shell
brew install node pnpm
pnpm create playwright
```

## Getting started

Playwright needs to fetch its own versions of instrumented browsers.
Run the following on your machine

```shell
pnpm install
pnpm exec playwright install
```

It downloads Chromium, Firefox, Webkit, and also ffmpeg.

```commandline
du -hs ${HOME}/Library/Caches/ms-playwright
881M    /Users/jdanek/Library/Caches/ms-playwrigh
```

Use either the
[VS Code Playwright extension](https://playwright.dev/docs/getting-started-vscode)
or the IntelliJ one for nice UX.

Also try out [the UI mode](https://playwright.dev/docs/test-ui-mode) and the [codegen mode](https://playwright.dev/docs/codegen).

```shell
pnpm playwright test --ui
pnpm playwright codegen localhost:8787
```

The main differentiators of Playwright are
[auto-waiting](https://playwright.dev/docs/actionability),
the browser fetching seen above,
and integration and access to browser APIs (geolocation, ...).

Playwright test runner uses [fixtures](https://playwright.dev/docs/test-fixtures) injection, similarly to Pytest.

For debugging, run test with `--headed` and put `await page.pause()` somewhere the test.
This only works when you "run" and not "run with debug" the test in the IDE.

The HTML report captures screenshot on failure, so maybe that's enough to figure out the failure.

CI captures execution traces that can be opened in [the trace viewer](https://playwright.dev/docs/trace-viewer) and explored.

```shell
pnpm playwright show-trace path/to/trace.zip
```

