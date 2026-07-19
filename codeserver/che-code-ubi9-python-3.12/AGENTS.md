# che-code wrapper image — maintainer notes

## VS Code extensions: update procedure

Extensions are `.vsix` files committed to `utils/` via git-lfs, downloaded from
[Open VSX](https://open-vsx.org/) (NOT the Microsoft Marketplace — its license
prohibits redistribution outside Microsoft VS Code products).

### Step-by-step

1. **Check the che-code VS Code version.** The pinned `CHECODE_IMAGE` in
   `Dockerfile.konflux.cpu` determines compatibility. To find the VS Code
   version:

   ```bash
   # On a linux machine (macOS skopeo can't pull linux images):
   podman run --rm --entrypoint cat \
       registry.redhat.io/devspaces/code-rhel9:3.29 \
       /checode-linux-libc/ubi9/product.json | python3 -c "
   import json, sys
   print(json.load(sys.stdin)['version'])
   "
   ```

   As of che-code 3.29, this is VS Code **1.116.0**.

2. **Check each extension's engine constraint** on Open VSX:

   ```bash
   curl -sL 'https://open-vsx.org/api/ms-python/python' | \
       python3 -c "import json,sys; d=json.load(sys.stdin); \
       print(d['version'], 'engines:', d.get('engines',{}).get('vscode','?'))"
   ```

   The `engines.vscode` field (e.g., `^1.95.0`) must be satisfied by the
   che-code VS Code version. A `^1.110.0` constraint requires VS Code >= 1.110.

3. **Check for platform-specific builds.** Some extensions (e.g., `debugpy`)
   ship native binaries and publish per-platform `.vsix` files instead of a
   universal one:

   ```bash
   curl -sL 'https://open-vsx.org/api/ms-python/debugpy' | \
       python3 -c "import json,sys; print(list(json.load(sys.stdin).get('downloads',{}).keys()))"
   ```

   If the output lists platform names (`linux-x64`, `darwin-arm64`, etc.)
   instead of `['universal']`, the extension has native components. **Only
   universal extensions** can be baked into this multiarch image. Platform-
   specific extensions must be left for users to install at runtime from the
   gallery (che-code defaults to Open VSX).

4. **Download the new `.vsix`:**

   ```bash
   # Example: ms-python.python version 2026.4.0
   curl -sLO 'https://open-vsx.org/api/ms-python/python/2026.4.0/file/ms-python.python-2026.4.0.vsix'
   ```

   URL pattern: `https://open-vsx.org/api/{namespace}/{name}/{version}/file/{namespace}.{name}-{version}.vsix`

5. **Replace the old `.vsix` in `utils/`, update the Dockerfile** install line
   with the new filename, and commit. git-lfs tracks `*.vsix` automatically.

6. **Run hadolint** to verify:

   ```bash
   hadolint --config ./ci/hadolint-config.yaml ./codeserver/che-code-ubi9-python-3.12/Dockerfile.konflux.cpu
   ```

### Known gaps

- **Pylance** (`ms-python.vscode-pylance`): proprietary, not on Open VSX.
  The Python extension falls back to Jedi for IntelliSense. This is a
  permanent gap unless Microsoft changes the Pylance license.

- **debugpy** (`ms-python.debugpy`): platform-specific (native debugger
  binaries). Published for linux-x64, linux-arm64, darwin-*, win32-* but
  **not** linux-ppc64le or linux-s390x. Users who need the Python debugger
  on amd64/arm64 can install it from the gallery at runtime.

- **Extension pack members**: `ms-toolsai.jupyter` declares an
  `extensionPack` with 4 members (renderers, keymap, cell-tags, slideshow).
  `ms-python.python` declares a pack with 3 members (pylance, debugpy,
  vscode-python-envs). When updating the main extension, check if the pack
  composition changed and update the members accordingly.

### Updating the che-code base image

There are two che-code images to keep in sync — they must ship the same
VS Code version:

| Track | Config file | Image |
|---|---|---|
| ODH | `build-args/cpu.conf` | `quay.io/che-incubator/che-code` (public, amd64+arm64) |
| RHOAI | `build-args/konflux.cpu.conf` | `registry.redhat.io/devspaces/code-rhel9` (subscription, +ppc64le+s390x) |

**Tag mapping is not 1:1.** Upstream tags (e.g., `7.120.0`) don't match
downstream tags (e.g., `3.29`). Match them by VS Code version:

```bash
# Check upstream VS Code version (on a linux machine):
podman run --rm --entrypoint cat \
    quay.io/che-incubator/che-code:7.120.0 \
    /checode-linux-libc/ubi9/product.json | python3 -c "
import json, sys; print(json.load(sys.stdin)['version'])"
# → 1.116.0

# Check downstream VS Code version:
podman run --rm --entrypoint cat \
    registry.redhat.io/devspaces/code-rhel9:3.29 \
    /checode-linux-libc/ubi9/product.json | python3 -c "
import json, sys; print(json.load(sys.stdin)['version'])"
# → 1.116.0  (must match)
```

**Steps to bump:**

1. Find the new downstream tag from the DevSpaces release.
2. Check its VS Code version (command above).
3. Find the upstream tag with the same VS Code version — check recent tags
   on [quay.io/che-incubator/che-code](https://quay.io/repository/che-incubator/che-code?tab=tags).
4. Get manifest list digests for both:

   ```bash
   skopeo inspect --raw docker://IMAGE:TAG | \
       python3 -c "import hashlib,sys; print('sha256:'+hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"
   ```

5. Update `CHECODE_IMAGE` in both `build-args/cpu.conf` and
   `build-args/konflux.cpu.conf` with `tag@sha256:digest`.
6. Verify all extension engine constraints still hold (see step 2 in
   "VS Code extensions: update procedure" above).
7. Re-audit the Che extensions — new releases may add or remove extensions
   from `/checode-linux-libc/ubi9/extensions/`.

### Build-args

- `build-args/cpu.conf` — ODH (CentOS Stream 9 base, PyPI-first)
- `build-args/konflux.cpu.conf` — RHOAI (UBI9 base, Red Hat ecosystem)

Both use the same `Dockerfile.konflux.cpu`. The `BASE_IMAGE` ARG selects
the Python base; `CHECODE_IMAGE` and `NODEJS_IMAGE` are the same for both.
