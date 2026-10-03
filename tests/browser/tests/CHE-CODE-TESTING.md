# che-code Playwright E2E Testing Guide

End-to-end testing of the che-code VS Code workbench image using Playwright.

## Architecture

```
┌──────────────┐     ┌───────────────────────────────────┐
│  Playwright  │────▶│  Chrome (--remote-debugging-port) │
│  Test Runner │     │         or CDP REPL               │
└──────────────┘     └──────────┬────────────────────────┘
                                │ HTTPS
                    ┌───────────▼───────────────────────┐
                    │  che-code container (port 8888)   │
                    │  ┌─────────┐    ┌──────────────┐  │
                    │  │  NGINX  │───▶│ VS Code 3100 │  │
                    │  │  (SSL)  │    │ server-main  │  │
                    │  └─────────┘    └──────────────┘  │
                    └───────────────────────────────────┘
```

### Test files

| File | Purpose |
|------|---------|
| `checode.spec.ts` | 6 smoke tests: editor load, welcome, terminal (fixme), Python ext, Jupyter notebook, activity tracker (fixme) |
| `models/codeserver.ts` | Page Object Model — shared with code-server tests (same VS Code DOM) |
| `fixtures.ts` | `CodeServerSource` discriminated union for URL vs container image |

### Running tests

```bash
# Against a running container (HTTPS)
CHECODE_URL=https://che-code-host:18888 \
  pnpm exec playwright test checode.spec.ts --project 'Google Chrome'

# Against a container started by testcontainers
TEST_TARGET=localhost/notebooks:che-code-test \
  pnpm exec playwright test checode.spec.ts --project 'Google Chrome'

# Single test
CHECODE_URL=https://che-code-host:18888 \
  pnpm exec playwright test checode.spec.ts --grep 'jupyter' --project 'Google Chrome'
```

## HTTPS Requirement

VS Code notebook webviews use `crypto.subtle` for content security. This API is only
available in **secure contexts** (HTTPS or `localhost`). Without HTTPS, notebooks render
as blank pages with this console error:

```
'crypto.subtle' is not available so webviews will not work.
This is likely because the editor is not running in a secure context.
```

### Self-signed cert for testing

The `enable-ssl.sh` wrapper generates a self-signed cert and patches NGINX:

```bash
#!/bin/bash
set -euo pipefail

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/tls.key -out /tmp/tls.crt \
  -subj "/CN=che-code-test" 2>/dev/null

tmp=$(mktemp)
cp /etc/nginx/nginx.conf "$tmp"
sed -i 's/8888 default_server/8888 ssl default_server/' "$tmp"
sed -i '0,/server {/{ /server {/a\        ssl_certificate /tmp/tls.crt;\n        ssl_certificate_key /tmp/tls.key;
}' "$tmp"
cat "$tmp" > /etc/nginx/nginx.conf
rm -f "$tmp"

exec /opt/app-root/bin/run-che-code.sh
```

Start the container with:

```bash
podman run -d --name che-code-test -p 127.0.0.1:18888:8888 \
  -v /tmp/enable-ssl.sh:/tmp/enable-ssl.sh:ro,Z \
  localhost/notebooks:che-code-test \
  bash /tmp/enable-ssl.sh
```

Playwright accepts self-signed certs via `ignoreHTTPSErrors: true` in `playwright.config.ts`.

In production, Kubeflow's OAuth proxy terminates TLS upstream, so the container itself doesn't need SSL.

## VS Code Command Palette

The command palette is the primary way to invoke actions. Key behaviors:

### Fuzzy matching is unreliable

Typing `Create: New Jupyter Notebook` may rank `Terminal: Create New Terminal` first.
The `runCommand` helper waits for the correct match before pressing Enter:

```typescript
async function runCommand(page: Page, command: string) {
  await page.keyboard.press('Control+Shift+P');
  await page.waitForSelector('.quick-input-widget', { timeout: 5000 });
  await page.keyboard.type(command, { delay: 50 });

  // Wait until the first row actually matches our command
  const pattern = new RegExp(command.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
  await expect(async () => {
    const firstLabel = await page.locator('.quick-input-widget .monaco-list-row')
        .first().getAttribute('aria-label');
    expect(firstLabel).toMatch(pattern);
  }).toPass({ timeout: 10000 });

  await page.keyboard.press('Enter');
}
```

### Clicking list rows fails

The quick-input list is virtualized. Rows that match but aren't in the visible viewport
have `element is not visible` and can't be clicked. **Always use `Enter`** to select the
first (filtered) match rather than clicking a specific row.

### Quick-input option selection

For multi-step pickers (e.g., kernel selection), filter by typing then press Enter:

```typescript
async function pickQuickInputOption(page: Page, text: string) {
  await page.keyboard.type(text, { delay: 30 });
  const option = page.locator('.quick-input-widget .monaco-list-row')
      .filter({ hasText: new RegExp(text, 'i') });
  await expect(option.first()).toBeVisible({ timeout: 10000 });
  await page.keyboard.press('Enter');
}
```

## Jupyter Notebook Testing

### Complete flow

```typescript
// 1. Create notebook
await runCommand(page, 'Create: New Jupyter Notebook');
await expect(page.locator('.tab').filter({ hasText: /\.ipynb/ }))
    .toBeVisible({ timeout: 30000 });

// 2. Select kernel (app-root has ipykernel pre-installed)
await page.getByRole('button', { name: /Select Kernel/i }).first().click();
await page.waitForSelector('.quick-input-widget', { timeout: 5000 });
// Python Env route needs `pet`, unavailable on ARM64 — use Jupyter Kernel instead
await pickQuickInputOption(page, 'Jupyter Kernel');
await expect(page.locator('.quick-input-widget').getByText(/Jupyter Kernel/i))
    .toBeVisible({ timeout: 10000 });
await pickQuickInputOption(page, 'app-root');

// 3. Wait for kernel picker to fully close
await expect(async () => {
  if (await page.locator('.quick-input-widget').isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
  }
  const snap = await page.ariaSnapshot();
  expect(snap).toContain('app-root');
  expect(snap).not.toMatch(/Select Kernel.*Jupyter Kernels/s);
}).toPass({ timeout: 30000 });

// 4. Type into cell
const cellEditor = page.locator('.cell-editor-container .monaco-editor');
await expect(cellEditor.first()).toBeVisible({ timeout: 10000 });
await cellEditor.first().click();
await page.keyboard.type('3 + 4');
await expect(page.locator('.cell-editor-container .view-line').first())
    .toContainText('3 + 4', { timeout: 5000 });

// 5. Execute and verify
await page.keyboard.press('Control+Enter');
await expect(async () => {
  const snap = await page.ariaSnapshot();
  expect(snap).toMatch(/\d+\.\d+s\s+Python/);
}).toPass({ timeout: 30000 });

// 6. Air-gap regression check
const snap = await page.ariaSnapshot();
expect(snap).not.toContain('Installing ipykernel');
```

### Kernel selection: why `app-root`

The container has multiple Python interpreters:

| Interpreter | ipykernel | Select by |
|------------|-----------|-----------|
| `+ Create Python Environment` | creates venv, installs at runtime | **Never** — breaks air-gap |
| `Python 3.12.13 /bin/python3.12` | yes (pip installed) | Works but may trigger install prompt |
| `app-root (Python 3.12.13) /opt/app-root/bin/python` | yes (pre-installed) | **Always** — reliable, air-gap safe |

If `Installing ipykernel: Installing collected package` appears as a notification,
it means the wrong interpreter was selected or ipykernel is missing from the image.
The test treats this as a failure.

### Cell output is inaccessible

The computed result (`7`) renders inside a VS Code webview iframe that Playwright
cannot access via locators, `page.frames()`, or shadow DOM traversal. Instead,
verify execution completed by checking the ARIA tree for execution time:

```typescript
// DON'T — output is in inaccessible webview iframe
await expect(page.locator('.cell-output-container')).toContainText('7');  // fails

// DO — check ARIA execution time
const snap = await page.ariaSnapshot();
expect(snap).toMatch(/\d+\.\d+s\s+Python/);  // e.g., "0.0s Python"
```

The ARIA tree does expose the execution count `[1]` and time `0.0s` in the cell
status area, which is sufficient to verify the cell ran successfully.

### Kernel picker may re-open

After selecting a kernel, VS Code sometimes re-opens the "Select Kernel" picker.
The test handles this by polling:

```typescript
await expect(async () => {
  if (await page.locator('.quick-input-widget').isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
  }
  const snap = await page.ariaSnapshot();
  expect(snap).toContain('app-root');
  expect(snap).not.toMatch(/Select Kernel.*Jupyter Kernels/s);
}).toPass({ timeout: 30000 });
```

## ARIA Snapshots

`page.ariaSnapshot()` (Playwright 1.59+) returns a YAML string of the accessibility
tree. It replaced the deprecated `page.accessibility.snapshot()`.

### Usage in tests

```typescript
const snap = await page.ariaSnapshot();

// Check kernel is connected
expect(snap).toContain('app-root');

// Check cell executed
expect(snap).toMatch(/\d+\.\d+s\s+Python/);

// Check no dialogs
expect(snap).not.toContain('Installing ipykernel');

// Scoped to a specific element
const navSnap = await page.locator('nav').ariaSnapshot();
```

### Useful patterns in the ARIA tree

```yaml
# Notebook tab
- tab "Untitled-1.ipynb" [selected]:

# Kernel name in toolbar
- button "/opt/app-root/bin/python":
- text: app-root (Python 3.12.13)

# Cell execution complete
- text:   0.0s Python

# Kernel picker open
- textbox "Type to choose a kernel source - Select Kernel":
- option "Python Environments...":

# Cell structure
- listitem "code cell":
    - button "Execute Cell (⌃Enter)":
    - code:
        - textbox "Editor content"
```

## Avoiding `waitForTimeout`

Every `waitForTimeout` is a test smell — replace with condition-based waits:

| Instead of | Use |
|-----------|-----|
| `waitForTimeout(1000)` after typing in picker | `expect(option).toBeVisible()` |
| `waitForTimeout(3000)` before screenshot | `waitForStableDOM(page, '.part.editor', 1000, 15000)` |
| `waitForTimeout(2000)` after kernel select | `expect(ariaSnapshot).toContain('app-root')` |
| `waitForTimeout(500)` after clicking cell | `expect(viewLine).toContainText('3 + 4')` |
| `waitForTimeout(1000)` after Escape | `expect(dialogOverlay).toBeHidden()` |

## CDP REPL (`scripts/pw-repl.ts`)

Interactive Playwright shell for exploring che-code's DOM without restarting tests.

### Setup

Launch a browser with CDP port exposed:

```typescript
const browser = await chromium.launch({
  headless: false,
  channel: 'chrome',
  args: ['--remote-debugging-port=9222']
});
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
await page.goto('https://che-code-host:18888/');
```

Note: Playwright defaults to `--remote-debugging-pipe`, not a TCP port.
You must pass `--remote-debugging-port=9222` explicitly.

### Connect the REPL

```bash
# Interactive
npx tsx scripts/pw-repl.ts 9222

# Single command
npx tsx scripts/pw-repl.ts 9222 --eval 'await page.screenshot({path: "/tmp/s.png"})'

# Script file
npx tsx scripts/pw-repl.ts 9222 --script /tmp/commands.js
```

### Available helpers

```typescript
pw> await dumpAria(page, /kernel|Python|cell/i)      // filtered ARIA lines
pw> await jsClick(page, '.some-selector')             // click via evaluate (bypasses viewport)
pw> await findTextInFrames(page, '7')                 // search all iframes
pw> await waitForLocator(page, '.my-element', 10000)  // poll for element existence
pw> await page.ariaSnapshot()                         // full accessibility tree
pw> expect(something).toBe(true)                      // Playwright expect
```

### CDP keyboard limitations

- `page.keyboard.type()` reaches the VS Code quick-input (command palette, kernel picker)
- `page.keyboard.type()` does **not** reach Monaco editor cells via CDP — the hidden
  `textarea.ime-text-area` is at `x: -49956` off-viewport
- **Fix**: `page.mouse.click(x, y)` at the visible cell coordinates, then `keyboard.type()`
- Non-active notebook tabs have cells at `x: -49956`; only the active tab's cells have
  positive viewport coordinates

```typescript
// Find the visible cell editor
const box = await page.evaluate(() => {
  for (const c of document.querySelectorAll('.cell-editor-container')) {
    const r = c.getBoundingClientRect();
    if (r.x > 0 && r.width > 0) return { x: r.x + 20, y: r.y + 15 };
  }
  return null;
});

// Click at those coordinates, then type
await page.mouse.click(box.x, box.y);
await page.keyboard.type('3 + 4');
```

This is a CDP-specific workaround. In direct Playwright tests (not CDP REPL),
`cellEditor.first().click()` works normally.

## IntelliJ Integration

### Run configuration

Playwright run configs use type `JavaScriptTestRunnerPlaywright`. Create in `.run/`:

```xml
<component name="ProjectRunConfigurationManager">
  <configuration name="che-code Playwright" type="JavaScriptTestRunnerPlaywright">
    <node-interpreter value="project" />
    <playwright-package value="$PROJECT_DIR$/tests/browser/node_modules/@playwright/test" />
    <working-dir value="$PROJECT_DIR$/tests/browser" />
    <envs>
      <env name="CHECODE_URL" value="https://che-code-host:18888" />
    </envs>
    <scope-kind value="ALL" />
    <method v="2" />
  </configuration>
</component>
```

### Debugging: `await` doesn't work in any IDE's evaluate expression

Neither IntelliJ nor VS Code can resolve `await` expressions in the debugger console
when paused at a breakpoint in a Playwright test. This is a **fundamental Node.js
limitation**, not an IDE bug.

**Root cause**: when the debugger pauses at a breakpoint, the Node.js event loop is
frozen. Promises cannot resolve because microtasks don't run while paused. The Chrome
DevTools Protocol's `Runtime.evaluate` has an `awaitPromise: true` flag, but it cannot
unfreeze the event loop either — it would need the paused execution to resume first,
which defeats the purpose of being paused.

**IntelliJ** ([WEB-25793](https://youtrack.jetbrains.com/issue/WEB-25793),
[WEB-53368](https://youtrack.jetbrains.com/issue/WEB-53368),
[WEB-66025](https://youtrack.jetbrains.com/issue/WEB-66025)):
returns `Promise {[[PromiseState]]: "pending", [[PromiseResult]]: undefined}` for any
async expression. Open since 2017, still unresolved as of 2026. A community plugin
[Evaluate Async Code](https://plugins.jetbrains.com/plugin/14476-evaluate-async-code)
exists but has limitations.

**VS Code** ([playwright#26687](https://github.com/microsoft/playwright/issues/26687)):
same behavior. The VS Code debug console wraps expressions with `awaitPromise: true`,
but this only helps for standalone promises, not for Playwright actions. As Playwright
maintainer Yury Semikhatsky explained:

> You cannot safely call asynchronous Playwright actions. This is a debugger limitation
> caused by paused microtasks and tasks in Node. Most actions will take effect
> immediately, even though their result promise won't resolve until execution is
> resumed, e.g. `page.getByRole('link').click()` will click the link. You can use this
> as a best effort workaround.

So `page.click(...)` fires the click but returns a pending promise. `expect(...)` based
assertions don't work at all because they rely on promise resolution for their result.

**Practical workarounds for Playwright debugging**:

1. **Step through**: write `await` calls as lines in the test, use F8 (Step Over) — each
   `await` resolves when you step past it
2. **CDP REPL** (`scripts/pw-repl.ts`): a separate Node.js process connected to the same
   browser via CDP. Its event loop is **not** paused, so `await` works normally
3. **`page.pause()`**: opens the Playwright Inspector (visual step-through, not a REPL)
4. **`playwright codegen`**: record interactions by clicking in the browser, generates
   test code with correct selectors

### `safeTimeout`

Test timeouts kill interactive debugging sessions. The `safeTimeout` helper skips
`test.setTimeout` when a debugger is attached:

```typescript
const DEBUGGER_ATTACHED = typeof (globalThis as any).v8debug === 'object'
    || /--inspect/.test(process.execArgv.join(' '));

function safeTimeout(t: TestType<any, any>, ms: number) {
  if (!DEBUGGER_ATTACHED) t.setTimeout(ms);
}
```

## Image-Level Issues Discovered

### Upstream vs downstream `server-main.js`

| | Upstream (`quay.io/che-incubator`) | Downstream (`devspaces/code-rhel9`) |
|---|---|---|
| HTML static paths | `./oss-dev/static/...` | `./oss-dev/static/...` |
| Serves `/oss-dev/static/` | **No** (404) | Yes (200) |
| Serves `/static/` | Yes (200) | Yes (200) |
| `server-main.js` size | 1,184,628 bytes | 1,185,553 bytes |

Fix: NGINX rewrite strips `oss-dev/` prefix. Harmless for downstream.

### `product.json` vs CLI flags

| Setting | `product.json configurationDefaults` | `product.json` field | CLI flag |
|---------|--------------------------------------|---------------------|----------|
| Workspace trust | Sets default, dialog still appears | `enableWorkspaceTrust` overridden by server | `--disable-workspace-trust` **works** |
| Extension quality | | `quality: "stable"` needed for install | |
| Telemetry | `telemetry.telemetryLevel: "off"` | | `--telemetry-level off` |
