#!/usr/bin/env node
// Patch product.json: update branding and inject configurationDefaults.

const fs = require("fs");

const path = process.argv[2] || "/checode-linux-libc/ubi9/product.json";
const d = JSON.parse(fs.readFileSync(path, "utf8"));

d.nameLong = "VS Code - Open Source Workbench";
d.serverApplicationName = "vscode-workbench";
d.welcomePageTitle = "VS Code - Open Source";
d.welcomePageSubtitle = "";
d.configurationDefaults = {
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.startupPrompt": "never",
  "telemetry.telemetryLevel": "off",
  "telemetry.enableTelemetry": false,
  "workbench.enableExperiments": false,
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "chat.disableAIFeatures": true,
};

fs.writeFileSync(path, JSON.stringify(d));
