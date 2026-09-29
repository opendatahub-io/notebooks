The `tests/browser` directory holds Playwright tests.

The following upstream projects have Playwright tests:

* JupyterLab (https://github.com/jupyterlab/jupyterlab/tree/main/galata)
* code-server (https://github.com/coder/code-server/tree/main/test)

Honorable mentions include:

* VSCode uses custom framework where Playwright is one of the possible runners (https://github.com/microsoft/vscode/wiki/Writing-Tests)

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
podman build \
  --build-arg PLAYWRIGHT_VERSION="$(python3 scripts/get_playwright_version.py)" \
  -t workbench-images-tests:latest \
  -f tests/browser/Dockerfile \
  tests/browser/
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

## Running the offline JupyterLab suite

The offline suite exercises JupyterLab through its visible browser UI while the
workbench and browser share a unique `--internal` container network. It does not
publish the Jupyter port and neither container receives a container-runtime
socket. The launcher also seeds a local bare Git remote as test fixture data;
the browser performs the file edit, staging, and commit through the Git panel.

Build or prepare both images while online, then run the launcher with local
images only. The launcher mounts the current offline spec and config into the
prepared browser image along with its page-object modules, so the executed source
is always the checked-out source:

```shell
podman pull quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:odh-stable
podman build \
  --build-arg PLAYWRIGHT_VERSION="$(python3 scripts/get_playwright_version.py)" \
  -t workbench-images-tests:latest \
  -f tests/browser/Dockerfile \
  tests/browser/

OFFLINE_BROWSER_IMAGE=workbench-images-tests:latest \
  tests/browser/scripts/run-offline-browser.sh
```

The default workbench image is the current `odh-stable` tag from the per-image
repository:
`quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:odh-stable`.
Use `OFFLINE_WORKBENCH_IMAGE` to select another preloaded image, and
`OFFLINE_RESULTS_DIR` to choose where logs, JUnit, traces, screenshots, and the
HTML report are written. `OFFLINE_STARTUP_TIMEOUT` and `OFFLINE_TEST_TIMEOUT`
bound startup and test execution. The browser and workbench use the
`/notebook/offline/` prefix. Set `OFFLINE_BASE_PATH` to use another local-only
prefix; the launcher passes the same value to both the workbench and Playwright.

These tests cover browser-visible notebook creation/execution and persistence,
file chooser upload and execution, terminal environment/file verification, and
local Git editing/staging/commit/history. Server-side setup is limited to
starting the image and preparing the isolated Git fixture; server API calls are
not used to satisfy feature assertions.

The baseline image starts the optional Kale extension. Without its external
service, JupyterLab may show the known Kale error dialog; the tests dismiss only
that exact dialog, annotate the test, and the launcher saves the workbench
`kale.log` beside the Playwright artifacts. Other dialogs remain test failures.

Each attempt uses UUIDs for created file names and its JupyterLab workspace to
avoid collisions across retries and repeated runs. UUIDs do not delete files:
the launcher removes the disposable containers and their files during teardown.

The spec describes workflows using `tests/models/jupyterlab/index.ts`; DOM
selectors live in `tests/models/jupyterlab/selectors.ts`. Navigation returns
typed views: `Launcher.newNotebook()` returns a `DraftNotebook`, `saveAs()`
returns a `SavedNotebook`, and `close()` returns a `FileBrowser`. Similarly,
`GitChanges.stage()` returns `StagedChanges`, which exposes `commit()` and
returns `GitHistory`. Assertions use named locators such as `cell.output` and
`editor.content`. These types guide valid next actions; TypeScript does not
invalidate older references after navigation, so use the returned view.

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
