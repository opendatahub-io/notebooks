---
name: che-code-development
description: Develop and validate the Che Code workbench image efficiently by mounting changed extensions, scripts, and runtime configuration into a disposable existing image before performing a full cached rebuild.
---

# Che Code development loop

Use this skill when changing the Che Code image, its extensions, entrypoint,
or runtime configuration. Keep browser feedback fast and reserve the full
image build for validation after the behavior works.

## Iterate in a disposable container

Start from an existing compatible image and mount the files being changed:

```bash
IMAGE="quay.io/opendatahub/workbench-images:che-code-codeserver-ubi9-python-3.12-3.6_20260917"
PLATFORM="linux/arm64"  # use linux/amd64 only when the image requires it
IMAGE_DIR="$PWD/codeserver/che-code-ubi9-python-3.12"

podman run --rm -it \
  --name che-code-dev \
  --platform "$PLATFORM" \
  -p 8888:8888 \
  -v "$IMAGE_DIR/extensions/kubeflow-github-authentication:/opt/app-root/checode/extensions/kubeflow-github-authentication:ro" \
  -v "$IMAGE_DIR/run-che-code.sh:/opt/app-root/bin/run-che-code.sh:ro" \
  "$IMAGE"
```

Add read-only mounts for other changed runtime files at the path where the
image reads them. For example, mount a changed nginx template over its copied
destination:

```bash
-v "$IMAGE_DIR/nginx/serverconf/proxy.conf.template:/opt/app-root/etc/nginx.default.d/proxy.conf.template:ro"
```

Mount the complete extension directory when changing its manifest or entry
point. Restart the disposable container after manifest, script, or
configuration changes so Che Code and nginx reread them. Keep browser console
and container logs visible while testing.

Use the host-native architecture while iterating. On Apple Silicon prefer
`linux/arm64`; emulated `linux/amd64` startup and extension-host operations are
slow and do not validate native behavior. If the existing image is only amd64,
set `PLATFORM=linux/amd64` deliberately and record that limitation.

Not every source change is a runtime mount. Dockerfile changes, package
installation, base-image changes, and build-time transformations such as
patching Che Code's bundled files require a rebuild. When practical, validate
the generated runtime artifact in the disposable container first; do not make
a complete rebuild the default response to every edit.

## Rebuild after progress

Once the disposable flow works, build the complete image with normal caching:

```bash
PATH="$PWD/.venv/bin:$PATH" \
  /opt/homebrew/bin/gmake che-code-codeserver-ubi9-python-3.12 \
  PUSH_IMAGES=no CONTAINER_BUILD_CACHE_ARGS=
```

The empty `CONTAINER_BUILD_CACHE_ARGS` assignment preserves the normal cache
configuration. Do not use `--no-cache` unless stale output has been demonstrated
to be the cause. The full build is a validation step because package installs
and cross-architecture stages remain expensive even with cache hits.

Finally, start a fresh container from the exact newly built tag with no source
mounts. Repeat extension activation, device authentication, session reuse,
agent chat, sign-out, and terminal startup. A passing mounted-container test is
not sufficient evidence that copied files, permissions, and build-time patches
in the final image are correct.
