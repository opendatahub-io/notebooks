# Patches for code-server (v4.106.3) — overlay onto prefetch-input/code-server

This directory is **copied over** the read-only `prefetch-input/code-server` submodule during the build (Dockerfile `COPY`). Files here overwrite the corresponding paths under the code-server source. **Do not modify `prefetch-input/code-server`**; all editable changes belong in this patches tree. The script `apply-patch.sh` (run after the COPY) then patches the ripgrep/vsce-sign npm tarballs and applies `patches/series`.

---

## Registry-only npm deps (ProdSec / Cachi2)

**Why:** ProdSec requires that npm dependencies be declared only in `package.json` / `package-lock.json` and fetched as npm packages (registry). Cachi2/Hermeto prefetches **registry** `.tgz` URLs but does **not** prefetch `codeload.github.com` or git-ref URLs. So we use **registry versions only** for everything that must be prefetched in Konflux.

**What changed:**

1. **custom-packages/**  
   - Pins deps that are prefetched and then consumed at build by `rewrite-npm-urls.sh`. Lockfiles in the repo use **https://registry.npmjs.org/...** URLs only so Konflux/Hermeto Prefetch-dependencies can fetch them (file:// is not accessible at prefetch time). At build time the script rewrites resolved URLs to the cache (file:// or https mirror per CACHI2_BASE).  
   - **@parcel/watcher**: was `codeload.github.com/parcel-bundler/watcher/tar.gz/<ref>` → now **registry** `@parcel/watcher@2.5.6` (tarball URL in package.json).  
   - **@emmetio/css-parser**: was `codeload.github.com/ramya-rao-a/css-parser/tar.gz/<ref>` (fork) → now **registry** `@emmetio/css-parser@0.4.1` (official package).  
   - **@playwright/browser-chromium**: unchanged (already registry).

2. **lib/vscode/package.json** and **lib/vscode/package-lock.json**  
   - **@parcel/watcher**: upstream had `parcel-bundler/watcher#<commit>`. Overridden to **`2.5.6`** with registry `resolved` URL so Cachi2 prefetches it and the rewrite script points npm at the same tarball.  
   - **Lockfile must include nested picomatch 4.0.3:** `@parcel/watcher@2.5.6` depends on `picomatch ^4.0.3`; the lockfile has a top-level `picomatch` at 2.3.1 (for other deps), so we **must** have an entry for `node_modules/@parcel/watcher/node_modules/picomatch` with version `4.0.3` and `resolved` to the registry tarball. Without it, `npm ci --offline` tries to fetch the packument for picomatch@^4.0.3 and fails with ENOTCACHED. When **regenerating** this lockfile, run `npm install` in `lib/vscode` (with network) so npm resolves the full tree and the generated lockfile contains this nested entry; then commit the updated lockfile.

3. **lib/vscode/remote/package.json** and **package-lock.json**  
   - Same **@parcel/watcher** override: dependency and lockfile entry set to **`2.5.6`** with registry URL (remote extension host / vscode-reh).  
   - **Lockfile must include nested picomatch 4.0.3:** postinstall.js runs `npm ci` in **lib/vscode/remote** as well; add `node_modules/@parcel/watcher/node_modules/picomatch` with version `4.0.3` and `resolved` as for lib/vscode. When regenerating, run `npm install` in `lib/vscode/remote` (with network).

4. **lib/vscode/extensions/package.json** and **package-lock.json**  
   - **@parcel/watcher** (devDependency) overridden to **`2.5.6`** with registry URL so all code-server npm trees use the same version.  
   - **Lockfile must include nested picomatch 4.0.3:** same as `lib/vscode/` — the root postinstall runs `node build/npm/postinstall.js`, which runs `npm ci` in **lib/vscode/extensions**. That run needs `node_modules/@parcel/watcher/node_modules/picomatch` with version `4.0.3` and `resolved` in the lockfile, or npm will try to fetch the packument and fail with ENOTCACHED. When regenerating, run `npm install` in `lib/vscode/extensions` (with network) so the lockfile gets the nested entry.

5. **lib/vscode/extensions/emmet/package.json** and **package-lock.json**  
   - Upstream emmet extension may depend on the **ramya-rao-a/css-parser** fork (or a file/codeload URL). This overlay switches it to **@emmetio/css-parser@0.4.1** from the registry so Cachi2 can prefetch it and ProdSec sees only npm packages.

6. **ci/dev/postinstall.sh**  
   - Runs `install-deps custom-packages` **before** `install-deps lib/vscode`. That way, during the single root `npm ci --offline`, postinstall installs custom-packages first (from rewritten file:// URLs), filling `~/.npm/_cacache` with @parcel/watcher and picomatch, so lib/vscode’s `npm ci` finds them and does not hit ENOTCACHED.

7. **lib/vscode/build/gulpfile.reh.js**  
   - Adds **ppc64** and **s390x** to `BUILD_TARGETS` so we can run the native gulp task (`vscode-reh-web-linux-ppc64-min` etc.) with system Node only (like che-code). Without this overlay, VS Code only defines tasks for linux x64, armhf, arm64, alpine.  
   - On ppc64le, Node reports `process.arch` as **"ppc64"** (not ppc64le), so the cache dir is `.build/node/.../linux-ppc64/` and the gulp task is `vscode-reh-web-linux-ppc64-min`. On s390x, `process.arch` is **"s390x"**.

8. **ci/build/build-vscode.sh**  
   - Builds for current arch (no x64 fallback on ppc64le/s390x). Uses system Node from `setup-offline-binaries.sh` cache.

All of the above are **overlays**: at build time the Dockerfile copies this patches tree on top of the read-only `prefetch-input/code-server` submodule, so every `package.json` / `package-lock.json` that referenced the old git/codeload refs is replaced by these files and thus uses the registry versions we define here.

**Argon2 (no prefetch):**  
- The root code-server dependency **argon2** (password hashing in `src/node/util.ts`) uses **node-pre-gyp** with install script `node-pre-gyp install --fallback-to-build` (see [node-argon2 package.json](https://github.com/ranisalt/node-argon2/blob/v0.31.2/package.json)). We set `npm_config_argon2_binary_host_mirror` to the hermetic deps path so it never hits the network; when the prebuild tarball is missing there, node-pre-gyp falls back to building from source via node-gyp. No prefetch of argon2 prebuilds; gcc-toolset-14 in rpm-base provides the compiler.

**Version notes (compatibility):**  
- **@parcel/watcher 2.5.6**: The old ref was commit `1ca032aa` (Aug 2025) — “Don’t show error messages when checking if watchman is available” (#198). That commit is **included in 2.5.6** (released Jan 2026); the 2.5.x line is linear after it. So 2.5.6 is a **safe upgrade** and keeps the same watchman behavior.  
- **@emmetio/css-parser 0.4.1**: The ramya-rao-a fork ref `370c480ac` (2017) only added **pre-built dist/** so GitHub-URL installs work without a build. The official npm package **already ships dist/**; there are no API or behavior changes. 0.4.1 is the **same parser**, properly versioned — safe to use. If you ever need the exact fork, publish it to an internal registry and point the dependency there.
