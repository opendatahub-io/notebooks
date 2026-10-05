# 19. TypeScript JupyterLab test organization and developer ergonomics

Date: 2026-09-27

## Status

Proposed

## Context

The JupyterLab browser tests need maintainable code organization and convenient,
discoverable APIs without weakening what they verify. Initial feature tests mixed
workflow steps, selectors, dialog handling, and asynchronous navigation in one
spec. Extracting helpers improved separation, but returning a different page
object after each asynchronous action introduced intermediate variables and
repeated `await` expressions.

This record captures the research and prototype work so far. Its scope is
TypeScript JupyterLab tests, page objects, selector organization, type-guided
navigation, and developer quality-of-life features. Container isolation and
feature coverage are included as experimental context, not as networking or CI
architecture decisions.

Related material:

- [ADR 0012: TypeScript developer tooling](0012-typescript-developer-tooling.md)
  establishes the existing typechecking and linting baseline.
- [Browser test conventions](../../../tests/browser/AGENTS.md) and
  [browser test documentation](../../../tests/browser/README.md) describe the
  current tooling and execution commands.
- The prototype comprises the
  [JupyterLab spec](../../../tests/browser/tests/jupyter-offline.spec.ts),
  [page objects](../../../tests/browser/tests/models/jupyterlab/index.ts), and
  [selector module](../../../tests/browser/tests/models/jupyterlab/selectors.ts).

## Decision

No implementation option is selected. This ADR remains proposed and records
requirements, alternatives, evidence, limitations, and questions for evaluation.
The existence of a working prototype does not establish it as the chosen
architecture. No proxy, generator, decorator, wrapper convention, dependency,
lint configuration change, or suite-wide migration is approved by this record.

## Desired properties

- Specs describe user workflows and keep their substantive assertions visible.
- Raw selectors and UI-specific knowledge have identifiable owners rather than
  being repeated throughout specs.
- Dot completion exposes related operations in context, such as `lab.files`,
  `notebook.cells`, or `history.entry(message)`.
- Navigation produces useful values, with types communicating valid next steps.
- Authoring avoids unnecessary ceremony without concealing execution order,
  failures, or state changes.
- Autocomplete, argument hints, documentation, rename, go-to-definition, traces,
  and linting remain useful.
- Test data, retries, cleanup, and assertions remain correct independently of
  the API syntax chosen.

## Research and alternatives

### 1. Page objects and selector ownership

The organizing idea discussed as the "power of the dot" is discoverability:
developers can start from an object and find relevant operations instead of
remembering free-function names and repeatedly passing a `Page` argument. This
does not require inheritance; classes, factory-created objects, and grouped
functions can provide different degrees of that organization. The slide
attribution mentioned during discussion was not independently verified.

The prototype separates three responsibilities:

| Layer | Example responsibility |
|---|---|
| Spec | Execute a workflow and assert persisted source or output |
| Page/component object | Navigate, handle expected dialogs, return the next view |
| Selector library | Locate a notebook cell, file row, menu command, or Git control |

Named locators such as `cell.output` and `editor.content` let specs retain
Playwright assertions without embedding CSS or accessible-name matching rules.
The current spec contains no raw selectors. This follows the general role of
[Playwright page objects](https://playwright.dev/docs/pom), while the exact
module boundaries remain an option for this repository.

Alternatives include colocating locators with each component, a shared selector
module, or a combination. Colocation limits indirection; a shared module makes
the DOM contract easy to audit but can become a large catalog. Classes provide
encapsulation; factory objects avoid some constructor boilerplate. Neither
approach inherently guarantees stable selectors or meaningful assertions.

Browser investigation exposed concrete details worth encapsulating: first save
opens a naming dialog; notebook and text editors have different save commands;
Git staging buttons appear on hover; clicking a selected sidebar tab collapses
it; History may already be expanded; terminal output can be rendered on a
canvas. These are UI behaviors, not reasons to put selectors back into specs.

### 2. Navigation results and lightweight typestate

The prototype models transitions including:

```text
Launcher -> DraftNotebook -> SavedNotebook -> FileBrowser
GitChanges -> StagedChanges -> GitHistory
```

For example, a draft exposes `saveAs(name)`, a saved notebook exposes `rename()`
and `close()`, and a staged Git view exposes `commit()`. Navigation returns the
next view; operations that remain on the same view can return `this`.

These types guide authoring. They do not prove the live DOM state, prevent a
user from changing the UI, or invalidate an older object after navigation.
TypeScript does not supply linear ownership here. A saved notebook also does
not necessarily mean it has no unsaved edits. View granularity, terminology,
runtime readiness checks, and stale-reference handling remain design questions.

### 3. Asynchronous navigation syntax

The existing explicit form is:

```ts
const lab = await JupyterLab.open(page, testInfo);
const launcher = await lab.openLauncher();
const draft = await launcher.newNotebook();
```

The requested fluent form is:

```ts
const draft = await JupyterLab.open(page, testInfo)
  .openLauncher()
  .newNotebook();
```

These are not interchangeable with the existing return types. An `async`
function returns a promise, and property access occurs before the outer
`await`. Making only `open()` or `load()` synchronous is insufficient if
`openLauncher()` still returns `Promise<Launcher>`.
[JavaScript async function semantics](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function)
explain this constraint.

| Option | Benefits | Costs or constraints |
|---|---|---|
| Separate awaited statements | Ordinary types, visible sequencing, convenient debugging points | Intermediate variables and repeated awaits |
| Nested awaits | No new abstraction | Parentheses become difficult to scan as the chain grows |
| Native `.then()` composition | Standard promises, explicit result propagation | Callback syntax rather than direct navigation chaining |
| Composite workflow methods, such as `lab.newNotebook()` | Hide routine intermediate navigation with little infrastructure | Can accumulate overlapping helpers or obscure steps relevant to a particular test |
| Synchronous entry with asynchronous initialization | Can separate construction from readiness | Alone does not enable fluent async transitions; initialization reuse and failure behavior need definition |
| Explicit deferred view wrappers | Each intermediate method returns a typed wrapper synchronously | Repeated wrapper classes and forwarding methods |
| Generated deferred wrappers | Reduce handwritten repetition while retaining concrete source | Generator, regeneration policy, generated diffs, and signature preservation |
| Generic typed thenable proxy | One forwarding mechanism with types derived from page objects | Promise semantics, diagnostics, and runtime forwarding need careful implementation |

Explicit deferred wrappers can support the desired syntax without making every
wrapper thenable: intermediate methods return another wrapper synchronously,
and the final method returns a native promise. If every intermediate stage
must itself be awaitable, a thenable contract is additionally needed.

Playwright's fluent locator construction and asynchronous navigation are
different operations: locator-building methods return locators, while actions
such as `click()` return promises. See the
[Locator API](https://playwright.dev/docs/api/class-locator). Cypress has a
[command queue](https://docs.cypress.io/app/core-concepts/introduction-to-cypress#The-Cypress-Command-Queue)
with its own execution model. Similar surface syntax does not make these
semantics interchangeable; no Cypress integration is proposed here.

### 4. Typed thenable proxies and autocomplete

A proxy does not inherently require an untyped interface. A mapped type can
derive methods from each page-object type and transform their return values.
The following methods-only type was explored:

```ts
type Method = (...args: never[]) => unknown;

type Chain<T> = PromiseLike<T> & {
  [K in keyof T as
    K extends 'then' ? never :
    T[K] extends Method ? K : never
  ]: T[K] extends (...args: infer A) => infer R
    ? (...args: A) => Chain<Awaited<R>>
    : never;
};
```

[Mapped types](https://www.typescriptlang.org/docs/handbook/2/mapped-types.html)
provide member transformation and filtering;
[conditional types](https://www.typescriptlang.org/docs/handbook/2/conditional-types.html)
provide argument and result inference; and
[`Awaited`](https://www.typescriptlang.org/docs/handbook/utility-types.html#awaitedtype)
models unwrapping. This example is a type-level exploration, not a complete
proxy implementation or an adopted public API.

A TypeScript language-service probe against the actual page objects reported:

| Expression state | Completion results |
|---|---|
| Pending JupyterLab | `openLauncher`, `then` |
| Pending Launcher | `newNotebook`, `newTerminal`, `then` |
| Awaited DraftNotebook | `cells`, `panel`, `saveAs` |

Expected-error checks also confirmed that creating a notebook directly on the
pending lab, or saving a notebook through the launcher, remained type errors.
The probe finished without unexpected diagnostics. This establishes compiler
and language-service behavior for these types; it does not establish equivalent
completion, documentation, or navigation quality in every IDE.

The example exposes methods while pending and ordinary properties after
awaiting. Chaining through properties such as `files` or `cells` would require
additional design. Generic and overloaded methods need further evaluation;
conditional inference over overloads does not generally preserve the full
overload set. Private/protected members are not part of the public mapped API.

### 5. Returning a thenable from `open()` consistently

Both an opt-in `chain(JupyterLab.open(...))` adapter and an entry point that
always returns `Chain<JupyterLab>` were discussed. The latter could retain
ordinary `await JupyterLab.open(...)` usage while supporting direct chaining.
It would nevertheless change the public return type from a native promise to
a custom awaitable.

Questions and implementation obligations include:

- **Unwrapping:** Does awaiting yield the ordinary page object? In the explored
  model it does, so subsequent methods again return ordinary promises. Returning
  the same thenable from its own resolution would risk recursive assimilation.
- **Entry-point declaration:** An always-fluent entry point must return its
  wrapper synchronously. Declaring that entry point `async` would assimilate the
  thenable into a native promise and lose immediate fluent access.
- **Promise surface:** `PromiseLike<T>` supplies `then`, not the full native
  promise API. Support for `catch`, `finally`, inspection, and native-promise
  interoperability requires a defined contract.
- **Execution:** Eager execution versus deferred execution, single execution
  across repeated awaits, and propagation of synchronous and asynchronous
  failures need explicit behavior.
- **Forwarding:** Method calls must retain the underlying receiver, including
  methods using private state. Reserved keys, symbols, and inspection should
  not accidentally enqueue browser actions.
- **Concurrency:** Sequencing one chain does not serialize separate branches
  against the same page. Type-guided navigation does not eliminate races.
- **Diagnostics:** Shorter source must still lead to useful call sites, action
  traces, step names, and errors when a middle transition fails.

Native promise resolution assimilates thenables; see
[`Promise.resolve`](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/resolve).
The current browser lint configuration enables `no-floating-promises` without
`checkThenables`. That option defaults to false, so detecting dropped custom
thenables would require evaluating a configuration change and verifying it with
negative examples. See the
[rule documentation](https://typescript-eslint.io/rules/no-floating-promises/#checkthenables).

### 6. Generating wrappers

Concrete wrapper classes could be generated from page-object types using the
TypeScript compiler API. This would retain explicit members and potentially
clearer source navigation while avoiding handwritten forwarding boilerplate.
There is no implemented generator or measured editor comparison yet.

Evaluation would need to cover which classes and methods participate,
overloads, generics, optional arguments, inherited members, documentation,
visibility, and mappings between source and generated code. The policy for
committing generated files, detecting stale output, and running generation
locally or in CI is also open. Automatically deriving a mapped type avoids
generated files but is a different mechanism from generating concrete source.

### 7. Method decorators, class decorators, and function wrappers

Decorators can replace behavior at runtime. They do not automatically rewrite
the declaration's caller-visible TypeScript type. A method declared to return
`Promise<JupyterLab>` remains promise-typed to callers even if a decorator
returns a compatible replacement with additional members. A class decorator
similarly does not automatically expose a transformed class API.

The local TypeScript 6.0.3 probe used a compatible decorated return type of
`Promise<T>` intersected with an extra method. Calling the extra method through
the decorated declaration still produced a property-not-found diagnostic. The
equivalent higher-order function exposed the transformed return type and
compiled. See
[modern decorators](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-0.html#decorators)
and the [class decorator typing limitation](https://www.typescriptlang.org/docs/handbook/decorators.html#class-decorators).

A function-wrapper alternative could take this form:

```ts
class JupyterLab {
  static open = chainable(
    async (page: Page, testInfo: TestInfo): Promise<JupyterLab> => {
      // Initialize the session and return the ordinary page object.
    },
  );
}
```

This is schematic: `chainable` and the body are not implemented by this ADR.
Unlike decorator syntax, the initializer's transformed return type participates
in ordinary type inference. A recursively forwarding proxy could wrap only
the entry point rather than decorate every page-object method. Decorator-based
alternatives could instead pair runtime wrapping with explicit declarations or
code generation; their extra maintenance remains part of the comparison.

### 8. Test correctness independent of API syntax

Two reviews exposed concerns that fluent syntax alone cannot solve:

1. Names based only on `testInfo.retry` are not unique across repeated attempts
   or invocations against reused state. The prototype now uses UUIDs for
   generated filenames, workspace names, and Git test values. Random names
   prevent collisions; they do not delete orphaned files. The current launcher
   removes the disposable containers during teardown. A persistent external
   workbench would require a separate ownership and cleanup strategy.
2. An assertion that source contains a printed literal is a weak persistence
   check: the output text also happens to occur in the source. The lifecycle
   test now executes `print(1 + 1)`, checks output equal to `2`, then reopens the
   notebook and checks the exact source and exact saved output separately.

Tests also need observable UI effects. The terminal workflow types a command
through the terminal and verifies its generated file through the file browser
and editor; it does not infer success from text in a canvas. The Git workflow
edits, stages, commits, and verifies History through the UI. Server-side fixture
preparation is distinguished from the feature behavior being asserted.

### 9. Execution context and verification evidence

The research started with offline feature coverage against
`quay.io/opendatahub/workbench-images:jupyter-baseline-ubi9-python-3.12-3.6_20260918`.
The initial `--network=none` requirement was changed to an internal network so
the browser/client runner could communicate with the Jupyter server while
remaining isolated from external services. No separate network-none smoke test
was retained.

A runner on that network means a second container reaching the workbench by
its network alias. Host-side access through published ports was also considered.
In the tested macOS Podman setup, internal-network containers served requests
inside the network while connections through the published host port reset.
That observation motivated the experimental harness; it is not a universal
claim about every Docker or Podman configuration.

The launcher uses preloaded images, mounts the current spec, configuration, and
page-object modules into the runner, and retains test artifacts. Mounting the
current source corrected an early stale-image validation problem. Image pulls
and dependency installation are preparation steps, separate from offline test
execution. Cluster-only functionality remains outside this browser experiment.

| Evidence | Result and limitation |
|---|---|
| Browser implementation and adversarial review | Three review rounds addressed assertions, navigation, isolation, current-source execution, timeouts, and cleanup |
| Page-object extraction | All four browser workflows passed without retries in 53.7 seconds after fixing an already-selected sidebar toggle |
| UUID and source/output changes | All four browser workflows passed without retries in 56.9 seconds; no test-owned containers or networks remained |
| Companion API suite | Six tests passed; useful harness context, not evidence for a fluent TypeScript API |
| Launcher negative cases | Missing local image returned exit 2; bounded execution returned exit 124; cleanup was checked |
| Type and lint checks | Direct TypeScript and scoped ESLint checks passed; host pnpm 12 could not run the package.json5 scripts expected by the repository's pnpm 11 setup |
| Typed chain exploration | Compiler/language-service probe passed; no runtime proxy or generated wrapper has been exercised against JupyterLab |
| Decorator exploration | Compiler probe confirmed that runtime decoration alone does not expose the changed return type |

The image's optional Kale extension produced an unavailable-service dialog.
The prototype dismisses only the recognized dialog, annotates affected tests,
and retains `kale.log`. Passing core workflows does not establish that every
extension works offline. Unknown dialogs continue to fail tests.

The environment also contained unrelated test files that blocked broad lint or
default test collection. Scoped checks were used and reported as such. Moving
helpers into model modules changes which file-pattern-specific lint rules apply;
a clean scoped lint result is not proof of equivalent rule coverage. None of
these observations establishes suite-wide reliability or performance.

## Open questions and evaluation criteria

Before choosing an option, compare representative notebook, upload, terminal,
and Git workflows for:

- Authoring effort, intermediate variables, abstraction size, and ease of
  understanding a failing test.
- Selector reuse, component boundaries, assertion visibility, and access to
  ordinary Playwright locators when needed.
- Useful typestate distinctions without implying ownership or readiness
  guarantees that the types cannot enforce.
- Completion, argument hints, documentation, refactoring, and source navigation
  in the editors contributors actually use.
- Correct sequencing, receiver binding, repeated awaiting, rejection behavior,
  branch concurrency, and dropped-await detection for any deferred API.
- How much of the native promise interface is supported, and whether fluent
  wrapping is opt-in or the entry point's default return contract.
- Coverage of properties, overloads, generics, and inherited methods in derived
  types or generated wrappers.
- Diagnostic quality in traces and reports, including whether explicit
  Playwright steps improve failures inside a long chain.
- Lint coverage for helpers as well as specs, tooling compatibility, dependency
  cost, and any generation or migration burden.
- Isolation and cleanup when tests use a persistent workbench rather than the
  disposable harness used for the current experiment.

The next decision should distinguish type-level demonstrations from runtime
validation and should include both successful workflows and failure cases for
any newly introduced asynchronous infrastructure.

## Consequences

This proposal preserves the research and a common comparison framework without
selecting a coding convention. Existing tests and their current organization
remain an experimental baseline. Adoption, migration scope, implementation
details, and any tooling changes require a subsequent decision or an update to
this ADR's status and decision section.
