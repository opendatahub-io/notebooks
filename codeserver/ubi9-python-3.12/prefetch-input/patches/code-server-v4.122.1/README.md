# code-server v4.122.1 hermetic overlay

Files here are copied over the `prefetch-input/code-server` submodule during the
Dockerfile `rpm-base` stage (`COPY .../patches/code-server-${CODESERVER_VERSION}/`).

## Source patches
- `ci/build/build-vscode.sh` — native-arch REH: Copilot gulp step, `core-ci`, then `*-ci` package + system Node
- `ci/dev/postinstall.sh` — install `custom-packages/` before other npm trees
- `lib/vscode/build/gulpfile.reh.ts` — add linux ppc64/s390x `BUILD_TARGETS`
- `lib/vscode/build/lib/tsgo.ts` — tsc fallback on ppc64/s390x
- `lib/vscode/build/lib/extensions.ts` — serialize extension streams on low-memory arches
- `lib/vscode/build/npm/preinstall.ts` — skip node-gyp header download when `NPM_CONFIG_NODEDIR` set

## Registry-only npm overlays
- Pin `@parcel/watcher` / `@emmetio/css-parser` to registry tarballs (no git refs)
- Overrides: `web-tree-sitter@0.23.0` (s390x), `es5-ext` → `@unes/es5-ext`
- `custom-packages/` prefetches those pins + `@playwright/browser-chromium`
- `lib/vscode/build/vite`: pin `vite` to `npm:rolldown-vite@7.3.1` (offline-safe; not `@latest`)
- Override `@vscode/ripgrep` → `@vscode/ripgrep-universal@1.18.0` (telemetry-extractor still pulls the old name)

## Runtime Dependency Review pins
High/critical runtime CVEs cleared via npm overrides (refresh locks after changing):
- `lib/vscode` / `remote`: `undici@7.29.0`, `ip-address@10.3.1`, `tar@7.5.19`, `shell-quote@1.9.0`, `axios@1.18.0`, `form-data@4.0.6`, `ws@8.21.0` / `ws@7.5.11`
- `microsoft-authentication`: `@nevware21/ts-utils@0.14.0`, `form-data@3.0.5`
- `custom-packages`: `picomatch@4.0.5`

## Notes for v4.122.1
- Upstream ships `@vscode/ripgrep-universal` (static bins). Hermetic builds install the
  AIPCC/RHOAI `ripgrep` Python wheel and overwrite those binaries via
  `../replace-aipcc-ripgrep.sh` after `npm ci` / `build:vscode` / `release` (FIPS).
- Built-in Copilot requires `compile-copilot-extension-full-build` during `build:vscode`
- RHAIENG-6400 spike: `run-code-server.sh` sets `chat.disableAIFeatures: false` and
  `github-authentication.preferDeviceCodeFlow: true`. Customer GA still gated by Legal (RHAI-113).
- Upstream dropped `release:standalone`; use `KEEP_MODULES=1 npm run release` → `./release`
