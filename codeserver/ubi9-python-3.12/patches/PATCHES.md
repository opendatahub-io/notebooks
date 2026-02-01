# Patch rationale: prefetch-input vs patches

This document explains **why** each file under `patches/code-server/` differs from the original in `prefetch-input/code-server/`, and what to keep when syncing from upstream.

**Build install flow:** The Dockerfile uses `CI=1 npm ci --offline` at the root (not `npm install`). The **prefetch** `ci/dev/postinstall.sh` already uses `CI` to run `npm ci` in subdirs (test, lib/vscode); lib/vscode’s postinstall uses `npm_command` and runs `npm ci` in remote/, extensions/, etc. Because `npm ci` does not modify lockfiles, `resolved` URLs stay absolute (`file:///cachi2/...`) after the initial rewrite. No patch of postinstall.sh or build-vscode.sh is used; prefetch originals are used.

---

## 1. `ci/build-scripts/npm-postinstall.sh` → applied to `ci/build/npm-postinstall.sh`

| Location | Original (prefetch-input) | Patched |
|----------|----------------------------|--------|
| `install_with_yarn_or_npm()` npm branch | Always runs `npm install --unsafe-perm --omit=dev` | If `npm-shrinkwrap.json` exists: runs `npm ci --offline --omit=dev --unsafe-perm`; otherwise same as original |

**Why:** In an offline Cachi2 build, the release package has shrinkwraps with `file:///cachi2/...` URLs. `npm install` still hits the registry for metadata (e.g. resolving `tslib@*`), which fails with cache mode `only-if-cached` (ENOTCACHED). Using `npm ci --offline` when a shrinkwrap exists installs only from the lockfile and does not contact the registry.

---

## 2. `ci/build-scripts/build-release.sh` → applied to `ci/build/build-release.sh`

| Location | Original | Patched |
|----------|----------|--------|
| After `create_shrinkwraps` | (none) | Call `rewrite_cachi2_path` on `npm-shrinkwrap.json`, `lib/vscode/remote/npm-shrinkwrap.json`, and `lib/vscode/extensions/npm-shrinkwrap.json` when `/root/scripts/lockfile-generators/rewrite-cachi2-path.sh` exists |

**Why:** Shrinkwraps are generated with registry URLs. For offline install (e.g. in release-standalone), resolved URLs must point at the Cachi2 output (`file:///cachi2/...`). This rewrite runs in the image where that script is available.

---

## 3. `ci/build-scripts/build-standalone-release.sh` → applied to `ci/build/build-standalone-release.sh`

| Location | Original | Patched |
|----------|----------|--------|
| After `RELEASE_PATH+=-standalone` | — | Merge `lib/vscode/remote/package.json` into `$RELEASE_PATH/lib/vscode/package.json` and copy `lib/vscode/remote/package-lock.json` → `$RELEASE_PATH/lib/vscode/npm-shrinkwrap.json` (so lib/vscode in release-standalone uses the **patched** remote deps, including node-gyp and proc-log). Copy `ci/build/npm-postinstall.sh` → `$RELEASE_PATH/postinstall.sh` so the **patched** postinstall (npm ci --offline when shrinkwrap exists) is used. |
| Before `pushd "$RELEASE_PATH"` | — | Call `rewrite_cachi2_path` on the three shrinkwraps (root, lib/vscode, lib/vscode/extensions) when the rewrite script exists. |
| `pushd` block | `npm install --unsafe-perm --omit=dev` | Same, but postinstall (above) runs the patched script that uses `npm ci --offline` inside lib/vscode and extensions when shrinkwraps exist. |

**Why:** Release-standalone is a copy of the release dir; its `lib/vscode` would otherwise use the **unpatched** remote shrinkwrap (no node-gyp/proc-log, registry URLs). Merging the patched remote package.json and using the patched remote lockfile as `lib/vscode/npm-shrinkwrap.json` ensures node-gyp (and proc-log) are in the shrinkwrap so `node-pty`’s postinstall (`npx node-gyp configure`) finds node-gyp in node_modules and does not hit the registry. Overwriting postinstall ensures the install under lib/vscode/extensions uses `npm ci --offline` when a shrinkwrap exists.

---

## 4. `lib-vscode/remote/package.json`

| Change | Original | Patched |
|--------|----------|--------|
| Dependencies | (no node-gyp, proc-log) | **Added:** `"node-gyp": "^11.2.0"`, `"proc-log": "^5.0.0"` |

**Why:** `node-pty` has a postinstall that runs `npx node-gyp configure`. If node-gyp is not in the dependency tree, npx fetches it from the registry and offline builds fail (ENOTCACHED). Adding node-gyp (and proc-log, which node-gyp requires at runtime to avoid MODULE_NOT_FOUND) as direct dependencies ensures they are in the lockfile and then in the shrinkwrap, and are prefetched by Cachi2.

**Note:** Do not change other dependency versions when applying this patch (e.g. keep `@xterm/addon-search` at `^0.16.0-beta.118` as in the original).

---

## 5. `lib-vscode/remote/package-lock.json`

| Change | Original | Patched |
|--------|----------|--------|
| Lockfile | `tslib` only as transitive (`"tslib": "*"`); no node-gyp or proc-log entries | Pinned `tslib` (2.6.3) with resolved URL; added full lock entries for `node-gyp` and `proc-log` with resolved URLs |

**Why:** (1) So `npm ci --offline` does not need to resolve `tslib@*` (avoids registry and ENOTCACHED). (2) So node-gyp and proc-log are installed from the lockfile and appear in the shrinkwrap used by release and release-standalone. Cachi2 must be run **with these patched files** so those tarballs are in the Cachi2 output.

---

## Removed / not patched

- **ci/dev/postinstall.sh** and **ci/build-scripts/build-vscode.sh**: Not patched; identical to prefetch. Dockerfile uses prefetch originals. Postinstall already has `CI` → `npm ci`; build-vscode.sh needs no changes.
- **fix-shrinkwrap-paths.sh** (not under patches): Removed; never run. Shrinkwrap rewriting is in build-release.sh and build-standalone-release.sh.

## Other patched files

- **lib-vscode/package.json**, **package-lock.json**, **extensions/emmet/** (package.json, package-lock.json), **test/** (package.json, package-lock.json):** Dependency and lockfile content for offline/Cachi2.
- **lib-vscode/build-lib/fetch.js:** Offline mode: when `VSCODE_OFFLINE_CACHE` is set, serve Node binaries from local dir instead of fetching from network.
- **s390x.patch:** Architecture-specific patch (applied at build).

---

## Summary

| File | Purpose of patch |
|------|-------------------|
| npm-postinstall.sh | Use `npm ci --offline` when shrinkwrap exists (release-package install). |
| build-release.sh | Rewrite shrinkwrap resolved URLs to `file:///cachi2` after create_shrinkwraps. |
| build-standalone-release.sh | Merge remote package.json into release-standalone lib/vscode; copy remote lockfile as npm-shrinkwrap.json; copy patched postinstall; rewrite shrinkwrap URLs. |
| remote/package.json | Add node-gyp and proc-log for node-pty postinstall (offline). |
| remote/package-lock.json | Pin tslib; add node-gyp/proc-log with resolved URLs for Cachi2. |
| lib-vscode/build-lib/fetch.js | Serve Node binaries from VSCODE_OFFLINE_CACHE when set (offline build). |
| lib-vscode/package.json, package-lock.json, extensions/emmet/, test/ | Dependency content for offline build. |
