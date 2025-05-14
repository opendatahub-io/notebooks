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
```

Since pnpm skips running build scripts by default, just run `cypress install` manually.

```
╭ Warning ───────────────────────────────────────────────────────────────────────────────────╮
│                                                                                            │
│   Ignored build scripts: cypress.                                                          │
│   Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.   │
│                                                                                            │
╰────────────────────────────────────────────────────────────────────────────────────────────╯
```

```shell
pnpm cypress install
```

## Getting started

> https://learn.cypress.io/testing-your-first-application/installing-cypress-and-writing-your-first-test

Cypress operates in two modes,
the noninteractive `run` mode and the interactive `open` mode that is useful for development.

```shell
pnpm cypress run
pnpm cypress open
```

To specify base URL, set the environment variable.

```shell
BASE_URL=https://nb_name.apps.oc_domain/notebook/ns_name/nb_name pnpm cypress open --e2e --browser chrome
```

Upon first run, `cypress open` will ask to begin with either E2E or Component testing.
Choose E2e, and the following files are created if they did not exist before:

* `cypress.config.ts`: The Cypress config file for E2E testing.
* `cypress/support/e2e.ts`: The support file that is bundled and loaded before each E2E spec.
* `cypress/support/commands.ts`: A support file that is useful for creating custom Cypress commands and overwriting existing ones.
* `cypress/fixtures/example.json`: Added an example fixtures file/folder.

For any subsequent run, Cypress offers a choice of three test environments:

1. Chrome
2. Electron
3. Firefox

Pick Chrome and click `Start E2E Testing in Chrome` to confirm.

If there are no tests (specs) detected, Cypress offers to `Scaffold example specs` or to `Create new spec`.
To experience this and maybe experiment with example specs,
temporarily delete everything under `cypress/e2e/` and let Cypress refresh.

## Developing tests

Start `cypress open` in E2E mode with Chrome

```shell
BASE_URL=... pnpm cypress open --e2e --browser chrome
```

The `open` mode can be further enhanced by enabling the (currently experimental) Cypress Studio.

Use this to quickly scaffold the test steps and then refactor them to use page objects.

* https://docs.cypress.io/app/guides/cypress-studio
* https://www.selenium.dev/documentation/test_practices/encouraged/page_object_models/
* https://docs.cypress.io/app/core-concepts/best-practices#Organizing-Tests-Logging-In-Controlling-State

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

## Problems and how to solve them

See above for the execution model notes, and the Cypress trade-offs documentation.

### Browser runs out of memory

Often, the `cypress open` browser crashes with the following error message.

```
We detected that the Chrome Renderer process just crashed.

We have failed the current spec but will continue running the next spec.

This can happen for a number of different reasons.

If you're running lots of tests on a memory intense application.
  - Try increasing the CPU/memory on the machine you're running on.
  - Try enabling experimentalMemoryManagement in your config file.
  - Try lowering numTestsKeptInMemory in your config file during 'cypress open'.

You can learn more here:

https://on.cypress.io/renderer-process-crashed
```

The advice helps somewhat, but Elyra still keeps crashing from time to time in `cypress open`.

### Cross-origin testing

Prior to Cypress 14, the [`document.domanin`](https://developer.mozilla.org/en-US/docs/Web/API/Document/domain) would be automatically set by Cypress.
Now that it is no loger true, it is as the documentation says:

> You can visit two or more origins in different tests without needing cy.origin().
> (https://docs.cypress.io/app/guides/cross-origin-testing#What-Cypress-does-under-the-hood)

This is especially annoying when Dashboard, Workbench,
and OAuth server each live in a separate origin and one test needs to visit all three.

#### Solutions for cross-origin testing

* The origin for each test is pinned by wherever the first `cy.visit()` ends up going, taking redirects into account.
  * Always `cy.visit()` first the origin where the test needs to spend the most time.
* Use `cy.origin()` when needed. Beware that custom commands don't work on secondary origins unless `Cypress.require()` (experimental) is called!
* Reconfigure oauth-proxy to allow bearer token authentication, or skip auth altogether and expose workbench container directly.
  * https://github.com/openshift/oauth-proxy/issues/179#issuecomment-1202279241
  * https://github.com/openshift/oauth-proxy/blob/8d8daec87683f43a15c1d74f05cb0f2635dba04e/main.go#L76
* Write the tests so that only one origin needs to be touched in the test.
  * `cy.session()` can hold login cookies established in a `before` step.
  * `cy.request()` is not bound by origin restrictions, attempt to log in through API.

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

## Good practices

* https://playwright.dev/docs/best-practices
