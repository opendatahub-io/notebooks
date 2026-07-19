"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const fs = require("fs");

const ACTIVITY_FILE = "/tmp/last-activity";
const DEBOUNCE_MS = 5000;

function activate(context) {
    let lastWrite = 0;

    const touch = () => {
        const now = Date.now();
        if (now - lastWrite > DEBOUNCE_MS) {
            lastWrite = now;
            try {
                fs.writeFileSync(ACTIVITY_FILE, String(Math.floor(now / 1000)));
            } catch {
                // /tmp not writable — skip silently
            }
        }
    };

    const events = [
        vscode.workspace.onDidChangeTextDocument,
        vscode.window.onDidChangeActiveTextEditor,
        vscode.window.onDidChangeTextEditorSelection,
        vscode.window.onDidChangeTextEditorViewColumn,
        vscode.window.onDidChangeWindowState,
        vscode.window.onDidChangeTerminalState,
        vscode.window.onDidChangeActiveTerminal,
    ];

    for (const event of events) {
        context.subscriptions.push(event(touch));
    }

    touch();
}

function deactivate() {}
