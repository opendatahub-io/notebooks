# Building with RHEL-Subscribed (AIPCC) Base Images

The `Dockerfile.konflux.*` files build from AIPCC RHEL-based base images
(`quay.io/aipcc/base-images/...`) instead of the ODH CentOS Stream base images. These RHEL base
images require an active Red Hat subscription for `dnf` operations (upgrade, install).

This guide explains how to set up the subscription for local builds. The CI workflow
(`.github/workflows/build-notebooks-TEMPLATE.yaml`, lines 127-148) does the same thing
automatically using GitHub secrets.

## Prerequisites

- **podman** installed and running
- **macOS only**: Rosetta enabled for x86_64 emulation (see [macos-podman-rosetta.md](macos-podman-rosetta.md))
- Red Hat subscription credentials (org ID + activation key)

## Step 1: Extract Entitlement Certificates

Run `subscription-manager register` inside a UBI9 container, mounting host directories to capture
the generated certificates:

```bash
mkdir -p entitlement consumer

# On macOS (Apple Silicon), --platform=linux/amd64 is needed because UBI9 defaults
# to the native arm64 image which won't produce x86_64 entitlement certs.
# On Linux x86_64, you can omit --platform.
podman run \
  --platform=linux/amd64 \
  -v "${PWD}/entitlement:/etc/pki/entitlement:Z" \
  -v "${PWD}/consumer:/etc/pki/consumer:Z" \
  --rm -t registry.access.redhat.com/ubi9/ubi \
  /usr/sbin/subscription-manager register \
    --org=18631088 --activationkey=YOUR_ACTIVATION_KEY
```

Ask your team lead for the activation key, or create one at
[Red Hat Console > Activation Keys](https://console.redhat.com/insights/connector/activation-keys).

After this, `entitlement/` and `consumer/` contain the PEM certificate files.

## Step 2: Configure Podman to Auto-Mount Certificates

Tell podman to mount the certificates into every container it builds. The `mounts.conf` format
does not support quoting, so **run these commands from a directory whose path contains no spaces or
special characters**.

**macOS** (via podman machine SSH -- `/etc` is writable, `/usr` is not):

```bash
podman machine ssh "printf '$(pwd)/entitlement:/etc/pki/entitlement\n$(pwd)/consumer:/etc/pki/consumer\n' | sudo tee /etc/containers/mounts.conf"
```

**Linux**:

```bash
printf "%s/entitlement:/etc/pki/entitlement\n%s/consumer:/etc/pki/consumer\n" "${PWD}" "${PWD}" \
  | sudo tee /etc/containers/mounts.conf
```

> [!NOTE]
> The CI workflow writes to `/usr/share/containers/mounts.conf`, which also works on Linux.
> This guide uses `/etc/containers/mounts.conf` because it works on both Linux and macOS
> (the podman machine VM has a read-only `/usr`).

### Verify

```bash
podman run --rm --platform=linux/amd64 --user 0 quay.io/aipcc/base-images/cpu:3.4.0-1774635932 \
  bash -c "subscription-manager identity && subscription-manager refresh && dnf repolist"
```

You should see the system identity, "All local data refreshed", and a list of RHEL repos (including
EUS repos like `rhel-9-for-x86_64-appstream-eus-rpms`). If the certs are not mounted correctly,
you will see only UBI repos and an "Unable to read consumer identity" warning instead.

> [!TIP]
> The command above uses the CPU base image. If you are building a CUDA or ROCm target,
> substitute the matching base image from your target's `build-args/konflux.*.conf`.

For a stricter pass/fail check that actually validates CDN access (including EUS entitlements),
download metadata from one small EUS repo (~16 MB, ~6 seconds):

```bash
podman run --rm --platform=linux/amd64 --user 0 quay.io/aipcc/base-images/cpu:3.4.0-1774635932 \
  bash -c "subscription-manager refresh \
    && dnf makecache --repo=codeready-builder-for-rhel-9-x86_64-eus-rpms"
```

This will fail with a 403 error if the entitlement is missing or does not include EUS access.

## Step 3: Build

Build with the Konflux Dockerfile and the AIPCC base image. The build-args config files in
`build-args/konflux.*.conf` specify the correct base image and index URLs.

```bash
# Example: runtime-minimal CPU
podman build --no-cache \
  --platform=linux/amd64 \
  -f runtimes/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu \
  --build-arg BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-1774635932 \
  --build-arg PYLOCK_FLAVOR=cpu \
  -t my-runtime-minimal:latest \
  .
```

The build may take 30 seconds or more before producing any output while podman copies the build
context and inspects the base image. This is normal -- do not abort.

**Important: always use `--no-cache` for the first build after setting up subscription.** The
Dockerfile's `subscription-manager refresh` step always exits successfully (even when certs are
missing) and gets cached. If you previously ran a build without subscription set up, that broken
layer is cached and will be reused silently -- causing `dnf upgrade` to fail with 403 errors later
in the build. See [#3241](https://github.com/opendatahub-io/notebooks/issues/3241) for details.

The Makefile does **not** pass `--no-cache` by default, so if you had prior failed builds, run
the podman command directly with `--no-cache` first, then switch to the Makefile:

```bash
make runtime-minimal-ubi9-python-3.12 KONFLUX=yes
```

## Cleanup

When done, unregister the subscription to free the entitlement:

```bash
podman run \
  --platform=linux/amd64 \
  -v "${PWD}/entitlement:/etc/pki/entitlement:Z" \
  -v "${PWD}/consumer:/etc/pki/consumer:Z" \
  --rm -t registry.access.redhat.com/ubi9/ubi \
  /usr/sbin/subscription-manager unregister
```

And remove the mounts config:

```bash
# macOS
podman machine ssh "sudo rm /etc/containers/mounts.conf"

# Linux
sudo rm /etc/containers/mounts.conf
```

## Troubleshooting

### 403 errors on EUS repos

```text
Status code: 403 for https://cdn.redhat.com/content/eus/rhel9/...
```

The entitlement certificates are not being mounted into the build container, or the
`subscription-manager refresh` step in the Dockerfile is using stale data. Fix:

1. Verify certs exist: `ls entitlement/ consumer/`
2. Verify mounts work: run the verify command from Step 2
3. Build with `--no-cache` to avoid cached layers from failed attempts

### QEMU segfault on macOS

See [macos-podman-rosetta.md](macos-podman-rosetta.md) to enable Rosetta.

### Which Dockerfile and base image to use?

Each image directory has `build-args/` configs:

| Config file | Base image source | Dockerfile |
|---|---|---|
| `cpu.conf` / `cuda.conf` | ODH CentOS Stream | `Dockerfile.cpu` / `Dockerfile.cuda` |
| `konflux.cpu.conf` / `konflux.cuda.conf` | AIPCC RHEL (needs subscription) | `Dockerfile.konflux.cpu` / `Dockerfile.konflux.cuda` |
| `konflux.rocm.conf` | AIPCC RHEL (needs subscription) | `Dockerfile.konflux.rocm` |

## How the CI Does It

The CI workflow (`.github/workflows/build-notebooks-TEMPLATE.yaml`) follows the same pattern:

1. Runs `subscription-manager register` inside a UBI9 container ("Add subscriptions from GitHub secret" step)
2. Writes `mounts.conf` (same step)
3. Copies pull-secret for quay.io/aipcc access (same step)
4. Builds with `KONFLUX=yes` ("Build: make" step)

The `build-notebooks-pr-aipcc.yaml` workflow triggers these builds for PRs with
`subscription: true` and `konflux: true`.
