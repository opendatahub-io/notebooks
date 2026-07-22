---
name: vscode-web-testing
description: Test VS Code web and Che Code browser workflows, including command-palette navigation, extension activation, authentication, and stateful multi-tab flows.
---

# VS Code web testing

Use this skill when validating a VS Code web workbench in a browser, especially
when an extension opens a second tab or depends on browser-side polling.

Use browser automation that exposes page identities, accessibility snapshots,
console messages, and network-visible failures. Keep the Che Code page and any
OAuth page distinct; after every navigation, confirm which page is active
before typing or clicking.

For command-palette actions:

1. Open the palette and type `>` followed by enough of the command name to make
   the result list unambiguous.
2. Inspect the result order in the snapshot. Recently used commands can move
   ahead of the intended command.
3. Press Arrow Down only when the intended item is visibly below the current
   selection, then press Enter. Do not use a fixed Arrow Down sequence without
   inspecting the list.

For the GitHub device-authentication workflow, read
[`references/github-device-auth.md`](references/github-device-auth.md) before
testing. The key invariant is that Che Code's dialog must launch the browser
page through its **Open** action; manually opening the same URL does not start
the authentication poller.

Record both browser evidence (dialogs, account menu, console) and container
evidence (server and extension-host logs). Treat an authentication success and
an unrelated missing or broken Copilot extension as separate results.
