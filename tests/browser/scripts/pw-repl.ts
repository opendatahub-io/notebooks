#!/usr/bin/env npx tsx
// Connect to a Playwright-launched browser via CDP and interact.
//
// Interactive:  npx tsx scripts/pw-repl.ts 9222
// Batch:        npx tsx scripts/pw-repl.ts 9222 --eval 'await page.screenshot({path:"/tmp/s.png"})'
// Script file:  npx tsx scripts/pw-repl.ts 9222 --script /tmp/commands.js

import { chromium, type Page, type Browser, type BrowserContext, type Frame, type Locator } from 'playwright';
import { expect } from '@playwright/test';
import * as repl from 'node:repl';
import * as fs from 'node:fs';

const args = process.argv.slice(2);
const portArg = args.find(a => !a.startsWith('--')) ?? '9222';
const evalIdx = args.indexOf('--eval');
const evalCode = evalIdx >= 0 ? args[evalIdx + 1] : null;
const scriptIdx = args.indexOf('--script');
const scriptFile = scriptIdx >= 0 ? args[scriptIdx + 1] : null;

const endpoint = portArg.startsWith('ws://') ? portArg : `http://127.0.0.1:${portArg}`;

// --- Helper functions available in REPL and scripts ---

/** Wait for a locator to match at least one element (no visibility requirement). */
export async function waitForLocator(page: Page, selector: string, timeout = 10000): Promise<number> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const count = await page.locator(selector).count();
    if (count > 0) return count;
    await page.waitForTimeout(500);
  }
  throw new Error(`waitForLocator: "${selector}" not found after ${timeout}ms`);
}

/** Search all frames (including webview iframes) for text. */
export async function findTextInFrames(page: Page, text: string): Promise<{ frame: Frame; index: number } | null> {
  const frames = page.frames();
  for (let i = 0; i < frames.length; i++) {
    const body = await frames[i].locator('body').textContent().catch(() => '');
    if (body && body.includes(text)) return { frame: frames[i], index: i };
  }
  return null;
}

/** Click via JavaScript evaluate — bypasses viewport/overlay checks. */
export async function jsClick(page: Page, selector: string): Promise<void> {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel) as HTMLElement | null;
    if (!el) throw new Error(`jsClick: no element for "${sel}"`);
    el.click();
    el.focus();
  }, selector);
}

/** Dump ARIA lines matching a filter. */
export async function dumpAria(page: Page, filter: RegExp): Promise<string[]> {
  const snap = await page.ariaSnapshot();
  return snap.split('\n').filter(l => filter.test(l));
}

// --- Connection ---

async function connect(): Promise<{ browser: Browser; page: Page; contexts: BrowserContext[] }> {
  console.error(`Connecting to ${endpoint}...`);
  const browser = await chromium.connectOverCDP(endpoint);
  const contexts = browser.contexts();
  const pages = contexts.flatMap(c => c.pages());
  console.error(`Connected. ${pages.length} page(s): ${pages.map(p => p.url()).join(', ')}`);
  const page = pages[0];
  if (!page) { console.error('No pages found.'); process.exit(1); }
  return { browser, page, contexts };
}

async function runBatch(code: string) {
  const { browser, page, contexts } = await connect();
  try {
    // Wrap the code in a typed async function and compile it with TypeScript.
    // tsx (which runs this file) uses jiti under the hood — we piggyback on it
    // by writing a temp .ts file and importing it.
    const ts = await import('typescript');
    const wrappedTs = `
      import type { Page, Browser, BrowserContext, Frame } from 'playwright';
      import type { Expect } from '@playwright/test';
      export default async function run(
        page: Page, browser: Browser, contexts: BrowserContext[],
        waitForLocator: typeof import('./pw-repl').waitForLocator,
        findTextInFrames: typeof import('./pw-repl').findTextInFrames,
        jsClick: typeof import('./pw-repl').jsClick,
        dumpAria: typeof import('./pw-repl').dumpAria,
        expect: Expect,
      ) { ${code} }`;
    const { outputText, diagnostics } = ts.default.transpileModule(wrappedTs, {
      compilerOptions: { module: ts.default.ModuleKind.CommonJS, target: ts.default.ScriptTarget.ES2022, strict: false },
    });
    if (diagnostics && diagnostics.length > 0) {
      for (const d of diagnostics) console.error('TS:', ts.default.flattenDiagnosticMessageText(d.messageText, '\n'));
    }
    const mod: any = {};
    new Function('exports', 'require', outputText)(mod, require);
    const result = await mod.default(page, browser, contexts,
      waitForLocator, findTextInFrames, jsClick, dumpAria, expect);
    if (result !== undefined) console.log(result);
  } catch (err: any) {
    console.error('ERROR:', err.message ?? err);
    if (err.log) console.error('Call log:', err.log.join('\n'));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

async function runInteractive() {
  const { browser, page, contexts } = await connect();
  console.error('\nVariables: page, browser, contexts');
  console.error('Helpers: waitForLocator, findTextInFrames, jsClick, dumpAria');
  console.error('Example: await dumpAria(page, /cell|output|kernel/i)\n');

  const r = repl.start({ prompt: 'pw> ', useGlobal: true });
  r.context.page = page;
  r.context.browser = browser;
  r.context.contexts = contexts;
  r.context.waitForLocator = waitForLocator;
  r.context.findTextInFrames = findTextInFrames;
  r.context.jsClick = jsClick;
  r.context.dumpAria = dumpAria;
  r.context.expect = expect;
  r.setupHistory('.pw-repl-history', () => {});
  r.on('exit', async () => {
    console.error('Disconnecting.');
    await browser.close();
    process.exit();
  });
}

(async () => {
  if (evalCode) await runBatch(evalCode);
  else if (scriptFile) await runBatch(fs.readFileSync(scriptFile, 'utf8'));
  else await runInteractive();
})();
