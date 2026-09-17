# GitHub device authentication test

Use a disposable Che Code container and keep its browser page available while
the OAuth page is open.

1. Open the command palette and run `GitHub: Device Authentication`.
2. Wait for Che Code's device-code dialog. Capture the displayed code and the
   dialog actions.
3. Click **Open** in that dialog. This is required: the click launches the
   browser flow and starts Che Code's polling. Do not open
   `https://github.com/login/device` yourself in a new tab; entering the URL
   manually does not connect that page to Che Code's poller.
4. In the tab opened by Che Code, enter the displayed code and approve the
   GitHub authorization. Do not confuse the visual hyphen with an input field;
   fill only the actual code inputs.
5. Return to Che Code and wait for the dialog to close or report success. Open
   the Accounts menu and verify that the GitHub account is present.
6. Reload the workbench and verify the account remains available. If testing
   sign-out, remove the token and confirm the account disappears before
   repeating the flow.

Collect these diagnostics when the flow fails:

- Che Code accessibility snapshots before and after clicking **Open**.
- The OAuth tab URL and final page state.
- Browser console messages from both pages.
- Container logs filtered for `github`, `authentication`, `extension`, and
  `error`.

An account shown in Che Code proves provider registration and token persistence;
it does not prove that GitHub Copilot Chat is installed or activated. Validate
agent chat separately and report an `Unknown extension GitHub.copilot-chat`
error as an extension-packaging issue rather than an authentication failure.
