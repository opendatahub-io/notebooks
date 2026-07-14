# Hermetic build patch scripts

Scripts copied into the image build context and run during `Dockerfile.konflux.cpu`
**before** `npm ci` / VS Code compilation. They adapt the prefetched
`prefetch-input/code-server` submodule for offline, multi-arch builds.

## Scripts (repository root of `patches/`)

| Script | When it runs | Purpose |
| ------ | ------------ | ------- |
| [`apply-patch.sh`](apply-patch.sh) | Always (rpm-base stage) | Overlays `code-server-v4.112.0/`, applies upstream `patches/series`, ripgrep/vsce-sign/parcel-watcher fixes; invokes `tweak-gha.sh` when `GHA_BUILD=true` |
| [`setup-offline-binaries.sh`](setup-offline-binaries.sh) | Before npm install | Global npm offline config; serialises npm scripts on GHA (`foreground-scripts`, `maxsockets=1`) |
| [`codeserver-offline-env.sh`](codeserver-offline-env.sh) | npm / node-gyp env | Offline npm env vars; `npm_config_build_from_source=false` on GHA |
| [`tweak-gha.sh`](tweak-gha.sh) | GHA only | Lowers VS Code heap/parallelism; sets `build_from_source=false` in `.npmrc` files |
| [`copy-gha-native-bindings.sh`](copy-gha-native-bindings.sh) | GHA only, after `release:standalone` | Copies `.node` native bindings GHA `--ignore-scripts` skips |

## Version overlay

Per-release overrides live under [`code-server-v4.112.0/`](code-server-v4.112.0/README.md).
When bumping code-server, add a new `code-server-vX.Y.Z/` directory and update
`apply-patch.sh` / Dockerfile `CODESERVER_VERSION` as documented there.

## GHA vs Konflux

| Concern | Konflux / local (default) | GitHub Actions (`GHA_BUILD=true`) |
| ------- | ------------------------- | --------------------------------- |
| npm lifecycle scripts | Full `npm ci` | `--ignore-scripts` + selective rebuilds in [`postinstall.sh`](code-server-v4.112.0/ci/dev/postinstall.sh) |
| VS Code parallelism | Upstream defaults | Reduced via `tweak-gha.sh` |
| Native bindings after release | Built during postinstall | Copied via `copy-gha-native-bindings.sh` |
| Parcel watcher | Prefetched optional deps | No-op install script in `apply-patch.sh` |

`GHA_BUILD` is set in [`build-args/cpu.conf`](../../build-args/cpu.conf) and passed
by `.github/workflows/build-notebooks-TEMPLATE.yaml` for codeserver targets.
