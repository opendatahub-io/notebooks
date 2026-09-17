#!/usr/bin/env node
// Patch product.json: update branding and inject configurationDefaults.

const fs = require("fs");

const path = process.argv[2] || "/checode-linux-libc/ubi9/product.json";
const bundlePath = process.argv[3];
const githubAuthPath = process.argv[4];
const githubAuthBrowserPath = process.argv[5];
const githubAuthPackagePath = process.argv[6];
const d = JSON.parse(fs.readFileSync(path, "utf8"));

d.nameLong = "VS Code - Open Source Workbench";
d.serverApplicationName = "vscode-workbench";
d.welcomePageTitle = "VS Code - Open Source";
d.welcomePageSubtitle = "";
// Build quality channel ("stable" or "insider"). Without this, VS Code treats
// the build as Code-OSS and blocks --install-extension for extension-pack members
// with "not allowed to be updated in the current product quality 'undefined'".
// See: https://github.com/VSCodium/vscodium/wiki/Product.json
d.quality = "stable";
d.configurationDefaults = {
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.startupPrompt": "never",
  "telemetry.telemetryLevel": "off",
  "telemetry.enableTelemetry": false,
  "workbench.enableExperiments": false,
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "github-authentication.preferDeviceCodeFlow": true,
};
// This mirrors codeserver/ubi9-python-3.12/run-code-server.sh: the setting selects
// GitHub's device-token flow, while this allowlist permits the built-in GitHub
// authentication provider to be used by the same trusted extensions as Code Server.
d.trustedExtensionAuthAccess = [
  "vscode.git",
  "vscode.github",
  "github.vscode-pull-request-github",
  "github.copilot",
  "github.copilot-chat",
];

fs.writeFileSync(path, JSON.stringify(d));

if (bundlePath) {
  // product.json is read by the server, but the web client has this allowlist
  // compiled into workbench.js, so update the generated browser bundle too.
  const bundle = fs.readFileSync(bundlePath, "utf8");
  const original =
    'trustedExtensionAuthAccess:{github:["GitHub.copilot-chat"],"github-enterprise":["GitHub.copilot-chat"]}';
  const replacement =
    'trustedExtensionAuthAccess:{github:["GitHub.copilot-chat","GitHub.copilot","GitHub.vscode-pull-request-github","vscode.github","vscode.git"],"github-enterprise":["GitHub.copilot-chat","GitHub.copilot","GitHub.vscode-pull-request-github","vscode.github","vscode.git"]}';
  if (!bundle.includes(original)) {
    throw new Error(`Could not find the expected GitHub auth allowlist in ${bundlePath}`);
  }
  fs.writeFileSync(bundlePath, bundle.replace(original, replacement));
}

function patchDeviceCodeProvider(extensionPath) {
  const extension = fs.readFileSync(extensionPath, "utf8");
  // VS Code/Che Code web hosting is otherwise compatible with this provider,
  // but this bundled extension version advertises web-worker support as false;
  // the host filters it out unless we correct that stale capability flag.
  const deviceCodeOffset = extension.indexOf('device code');
  const capability = "supportsWebWorkerExtensionHost:!1";
  const capabilityOffset = extension.indexOf(capability, deviceCodeOffset);
  if (deviceCodeOffset < 0 || capabilityOffset < 0) {
    throw new Error(`Could not find the device-code provider in ${extensionPath}`);
  }
  fs.writeFileSync(
    extensionPath,
    extension.slice(0, capabilityOffset) +
      capability.replace("!1", "!0") +
      extension.slice(capabilityOffset + capability.length),
  );
}

function patchWebActivation(extensionPath) {
  const extension = fs.readFileSync(extensionPath, "utf8");
  // Che Code's remote extension host loads the main Node bundle, even though
  // the browser client also has a web-worker host. Both bundles otherwise
  // return after registering only the device-code command, so the built-in
  // `github` authentication provider is never registered for Copilot.
  const activationGuard =
    /if\(![A-Za-z_$][\w$]*\)\{[A-Za-z_$][\w$]*\([A-Za-z_$][\w$]*\);return\}/g;
  activationGuard.lastIndex = extension.indexOf("device code");
  const matches = [...extension.matchAll(activationGuard)];
  if (matches.length !== 1) {
    throw new Error(`Expected one GitHub web activation guard in ${extensionPath}, found ${matches.length}`);
  }
  const guard = matches[0][0];
  fs.writeFileSync(extensionPath, extension.replace(guard, guard.replace(";return", "")));
}

if (githubAuthPath) {
  patchDeviceCodeProvider(githubAuthPath);
  patchWebActivation(githubAuthPath);
}
if (githubAuthBrowserPath) {
  patchDeviceCodeProvider(githubAuthBrowserPath);
  patchWebActivation(githubAuthBrowserPath);
}

if (githubAuthPackagePath) {
  const packageJson = JSON.parse(fs.readFileSync(githubAuthPackagePath, "utf8"));
  // Che Code's web worker host can ask Copilot for the provider before the
  // normal authentication-request activation reaches the built-in extension.
  // Activate it eagerly so the provider is registered before agent chat starts.
  packageJson.activationEvents = ["*"];
  fs.writeFileSync(githubAuthPackagePath, JSON.stringify(packageJson));
}
