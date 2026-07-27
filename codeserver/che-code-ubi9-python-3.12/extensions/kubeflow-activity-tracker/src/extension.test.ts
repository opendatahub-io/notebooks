import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as vscode from 'vscode';
import { activate, ACTIVITY_FILE, DEBOUNCE_MS } from './extension';

vi.mock('vscode');
vi.mock('fs', () => ({
	writeFileSync: vi.fn(),
}));

import { writeFileSync } from 'fs';

describe('kubeflow-activity-tracker', () => {
	let context: vscode.ExtensionContext;
	let eventCallbacks: Array<() => void>;

	beforeEach(() => {
		vi.useFakeTimers();
		vi.mocked(writeFileSync).mockReset();

		eventCallbacks = [];

		const mockEvent = (_listener: (e: any) => void): vscode.Disposable => {
			eventCallbacks.push(_listener);
			return { dispose: vi.fn() };
		};

		vi.spyOn(vscode.workspace, 'onDidChangeTextDocument', 'get')
			.mockReturnValue(mockEvent as any);
		vi.spyOn(vscode.window, 'onDidChangeActiveTextEditor', 'get')
			.mockReturnValue(mockEvent as any);
		vi.spyOn(vscode.window, 'onDidChangeTextEditorSelection', 'get')
			.mockReturnValue(mockEvent as any);
		vi.spyOn(vscode.window, 'onDidChangeTextEditorViewColumn', 'get')
			.mockReturnValue(mockEvent as any);
		vi.spyOn(vscode.window, 'onDidChangeWindowState', 'get')
			.mockReturnValue(mockEvent as any);
		vi.spyOn(vscode.window, 'onDidChangeTerminalState', 'get')
			.mockReturnValue(mockEvent as any);
		vi.spyOn(vscode.window, 'onDidChangeActiveTerminal', 'get')
			.mockReturnValue(mockEvent as any);

		context = {
			subscriptions: [],
		} as unknown as vscode.ExtensionContext;
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	it('writes timestamp on activation', () => {
		vi.setSystemTime(new Date('2026-07-19T10:00:00Z'));

		activate(context);

		expect(writeFileSync).toHaveBeenCalledWith(
			ACTIVITY_FILE,
			String(Math.floor(Date.now() / 1000)),
		);
	});

	it('subscribes to all 7 events', () => {
		activate(context);

		expect(context.subscriptions).toHaveLength(7);
	});

	it('writes correct format (epoch seconds, not milliseconds)', () => {
		const epochMs = new Date('2026-07-19T10:00:00Z').getTime();
		vi.setSystemTime(epochMs);

		activate(context);

		const writtenValue = vi.mocked(writeFileSync).mock.calls[0][1] as string;
		const parsed = Number(writtenValue);
		expect(parsed).toBe(Math.floor(epochMs / 1000));
		expect(writtenValue).not.toContain('.');
	});

	it('debounce skips rapid writes', () => {
		vi.setSystemTime(new Date('2026-07-19T10:00:00Z'));

		activate(context);
		expect(writeFileSync).toHaveBeenCalledTimes(1);

		vi.advanceTimersByTime(1000);
		eventCallbacks[0]();

		expect(writeFileSync).toHaveBeenCalledTimes(1);
	});

	it('debounce allows write after interval', () => {
		vi.setSystemTime(new Date('2026-07-19T10:00:00Z'));

		activate(context);
		expect(writeFileSync).toHaveBeenCalledTimes(1);

		vi.advanceTimersByTime(DEBOUNCE_MS + 1);
		eventCallbacks[0]();

		expect(writeFileSync).toHaveBeenCalledTimes(2);
	});

	it('survives unwritable path', () => {
		vi.mocked(writeFileSync).mockImplementation(() => {
			throw new Error('EACCES: permission denied');
		});

		expect(() => activate(context)).not.toThrow();
	});
});
