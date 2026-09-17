import * as vscode from 'vscode';
import { writeFileSync } from 'fs';

export const ACTIVITY_FILE = '/tmp/last-activity';
export const DEBOUNCE_MS = 5000;

export function activate(context: vscode.ExtensionContext) {
	let lastWrite = 0;

	const touch = () => {
		const now = Date.now();
		if (now - lastWrite >= DEBOUNCE_MS) {
			try {
				writeFileSync(ACTIVITY_FILE, String(Math.floor(now / 1000)));
				lastWrite = now;
			} catch {
				// /tmp not writable — skip silently
			}
		}
	};

	const events: vscode.Event<any>[] = [
		vscode.workspace.onDidChangeTextDocument,
		vscode.window.onDidChangeActiveTextEditor,
		vscode.window.onDidChangeTextEditorSelection,
		vscode.window.onDidChangeTextEditorViewColumn,
		vscode.window.onDidChangeWindowState,
		vscode.window.onDidChangeTerminalState,
		vscode.window.onDidChangeActiveTerminal,
	];
	// The manifest enables terminalDataWriteEvent because this proposed API is
	// needed to refresh activity after the terminal's first interaction.
	const terminalDataEvent = (vscode.window as typeof vscode.window & {
		onDidWriteTerminalData?: vscode.Event<unknown>;
	}).onDidWriteTerminalData;
	if (terminalDataEvent) {
		events.push(terminalDataEvent);
	}

	for (const event of events) {
		context.subscriptions.push(event(touch));
	}

	touch();
}

export function deactivate() {}
