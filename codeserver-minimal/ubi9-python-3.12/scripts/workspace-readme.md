# Code Server workbench

Welcome to the Open Data Hub code-server workbench.

## GitHub Copilot (optional — bring your own)

This image **does not ship** GitHub Copilot or other proprietary AI binaries.
AI chat is **disabled by default**.

If you have your own **GitHub Copilot subscription** and want to enable it:

1. Open a **terminal** in this workbench (`Terminal → New Terminal`).
2. Run (script is on `PATH` at `/opt/app-root/bin/install-byo-copilot.sh`;
   a symlink `./install-byo-copilot.sh` is also in this folder):

   ```bash
   install-byo-copilot.sh
   ```

   You will be asked to accept GitHub/Microsoft Copilot terms before any download.
   For non-interactive use, pass `--accept-license`.

3. **Restart** the workbench (stop/start the container or workbench pod).
4. Reload this page, then **sign in to GitHub** when Copilot prompts you.

Run `install-byo-copilot.sh --help` for offline VSIX install and version pins.

> After you are familiar with the steps, you can stop opening this file on every
> start: set `workbench.startupEditor` to `none` in your user settings.

## Python

The default interpreter is `/opt/app-root/bin/python3`. See `.vscode/launch.json`
for the debugger configuration.
