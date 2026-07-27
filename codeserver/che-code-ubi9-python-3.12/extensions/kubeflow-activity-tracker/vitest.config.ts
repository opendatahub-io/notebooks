import { resolve } from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    // 'vscode' is a virtual module (not on disk); redirect to jest-mock-vscode shim
    alias: {
      vscode: resolve(import.meta.dirname, '__mocks__/vscode.ts'),
    },
  },
});
