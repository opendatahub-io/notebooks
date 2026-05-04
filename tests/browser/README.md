The `tests/browser` directory holds Playwright tests.

The following upstream projects have Playwright tests:

* JupyterLab (https://github.com/jupyterlab/jupyterlab/tree/main/galata)
* code-server (https://github.com/coder/code-server/tree/main/test)

Honorable mentions include:

* VSCode uses custom framework where Playwright is one of the possible runners (https://github.com/microsoft/vscode/wiki/Writing-Tests)
* RStudio components have Playwright tests (https://github.com/rstudio/shinyuieditor, https://github.com/rstudio/xterm.js)
* Some RStudio tests are implemented in private repository https://github.com/rstudio/rstudio/issues/10400, possibly in R https://github.com/rstudio/rstudio/tree/main/src/cpp/tests/automation with https://github.com/rstudio/chromote)

The following upstream projects have Cypress tests:

* Elyra (https://github.com/elyra-ai/elyra/tree/main/cypress)
* ODH Dashboard (https://github.com/opendatahub-io/odh-dashboard/tree/main/frontend/src/__tests__/cypress)

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

## Running the container image locally

Build the image:

```shell
podman build -t workbench-images-tests:latest -f tests/browser/Dockerfile tests/browser/
```

List available tests:

```shell
podman run --rm workbench-images-tests:latest --list --project=chromium
```

Run `@smoke` tests against an OCP cluster (requires `oc login` first):

```shell
podman run --rm -t \
  -e KUBECONFIG=/home/pwuser/tests/browser/.kube/config \
  -v "$HOME/.kube/config":/home/pwuser/tests/browser/.kube/config:ro,Z \
  -v "$(pwd)/results":/home/pwuser/tests/browser/results:Z \
  workbench-images-tests:latest \
  --project=chromium --grep @smoke
```

Test results (JUnit XML, screenshots) are written to the `results/` volume mount.

## Test tags and quality gates

Tests are tagged using [Playwright's tag API](https://playwright.dev/docs/test-annotations#tag-tests)
and filtered at runtime with `--grep @tagname`.

Each test should have at least one tier tag. The upstream RHOAI TestOps standard assigns exactly one tier per test; this repository allows multiple tier tags when a test is critical enough to run at several gates. The tier definitions follow the
[RHOAI TestOps quality gate standard](https://docs.google.com/document/d/1LNkQDDN1g--3UYmLzi_c8WZjNSNudzDmhRrqQ7IaDeM/edit?tab=t.0#heading=h.ef6799ef5ld5)
(agreed in `#wg-openshift-ai-quality`, Feb 2026):

| Tag | Gate | Meaning | Cadence |
|---|---|---|---|
| `@smoke` | Smoke | Very high / critical priority tests. Minimal validation that the component works at all. | Every nightly build |
| `@tier1` | Tier 1 | High-priority tests (excluding Smoke). Core functionality and common user workflows. | Daily on nightly builds |
| `@tier2` | Tier 2 | Medium/low-priority positive tests. Broader coverage, less critical paths. | Weekly |
| `@tier3` | Tier 3 | Negative and destructive tests. Error handling, edge cases, recovery scenarios. | Weekly |

A test that belongs to multiple tiers (e.g. a basic check that should run in every gate)
can carry multiple tags: `{ tag: ['@smoke', '@tier1', '@tier2', '@tier3'] }`.

Additional tags like `@codeserver` or `@openshift` group tests by feature area
and are orthogonal to the tier tags.

## Good practices

* https://playwright.dev/docs/best-practices
