#!/usr/bin/env node

/**
 * Offline-safe postinstall for agent-browser.
 *
 * The npm tarball ships native binaries for x64/arm64/darwin/win32 only.
 * ppc64le/s390x are not bundled; upstream postinstall then tries to download
 * from GitHub releases, which fails in hermetic Konflux builds (network
 * blocked) and crashes on unlink. This script chmods a bundled binary when
 * present, otherwise exits 0 and uses the Node.js CLI fallback.
 */

import { existsSync, chmodSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { platform, arch } from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');
const binDir = join(projectRoot, 'bin');

const platformKey = `${platform()}-${arch()}`;
const ext = platform() === 'win32' ? '.exe' : '';
const binaryName = `agent-browser-${platformKey}${ext}`;
const binaryPath = join(binDir, binaryName);

if (existsSync(binaryPath)) {
	if (platform() !== 'win32') {
		chmodSync(binaryPath, 0o755);
	}
	console.log(`Native binary ready: ${binaryName}`);
	process.exit(0);
}

console.log(
	`No bundled native binary for ${platformKey}; using Node.js CLI fallback`,
);
process.exit(0);
