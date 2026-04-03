# Enabling Rosetta for x86_64 Container Images on macOS (Apple Silicon)

Some container images in this project (notably the CUDA and aipcc-based images) are built only for
`linux/amd64`. On Apple Silicon Macs, podman uses QEMU by default to emulate x86_64, which can be
slow or crash with large images (segfaults are common with CUDA base images under QEMU).

Apple's **Rosetta** translation layer is significantly faster and more stable. Podman supports
Rosetta but ships with it **disabled by default** due to a past incompatibility between Rosetta and
Linux kernels 6.13+. Apple fixed the kernel-side crash in **macOS Tahoe** (macOS 26), but
podman-machine-os has not yet re-enabled Rosetta by default
([containers/podman-machine-os#212](https://github.com/containers/podman-machine-os/issues/212)),
so the manual trigger below is still required.

> [!NOTE]
> Rosetta support in the podman machine VM requires Podman 5.1.0 or later.

## Enabling Rosetta

Create the trigger file inside the podman machine VM and activate the systemd service:

```bash
# Create the trigger file and activate Rosetta (no machine restart needed)
podman machine ssh "sudo touch /etc/containers/enable-rosetta && sudo systemctl start rosetta-activation.service"

# Verify Rosetta is active
podman machine ssh "cat /proc/sys/fs/binfmt_misc/rosetta"
# Expected output starts with: enabled
```

This survives `podman machine stop` / `start` cycles (the trigger file is on `/etc` which persists).
However, `podman machine rm` followed by `podman machine init` wipes the VM state, so you need to
run the commands again after recreating a machine.

### Known issue: `podman machine inspect` may be misleading

`podman machine inspect` reports a `Rosetta` field in the machine config, but this config flag does
not reliably control whether Rosetta is actually active inside the VM
([containers/podman#28181](https://github.com/containers/podman/issues/28181)). Always verify with
the binfmt check above.

## Verifying it works

```bash
podman run --rm --platform=linux/amd64 registry.access.redhat.com/ubi9/ubi uname -m
# Should print: x86_64
```

If this prints `x86_64` without segfaulting, Rosetta is working.

## Troubleshooting

### QEMU segfault with CUDA images

If you see `qemu: uncaught target signal 11 (Segmentation fault) - core dumped` when pulling or
running a large amd64 image, enable Rosetta as described above.

### Rosetta activation fails

If `cat /proc/sys/fs/binfmt_misc/rosetta` shows nothing after the steps above, check:

```bash
podman machine ssh "systemctl status rosetta-activation.service"
podman machine ssh "ls -la /var/mnt/rosetta 2>/dev/null || echo 'rosetta mount missing'"
```

The Rosetta VirtioFS mount must be present at `/var/mnt/rosetta`. This requires macOS Tahoe (26)
or later.

### Installing packages inside the podman machine VM

The podman machine runs Fedora CoreOS, which has a read-only `/usr` filesystem. To install
debugging tools:

```bash
podman machine ssh
sudo bootc usr-overlay   # creates a transient writable overlay on /usr (lost on reboot)
sudo dnf install htop    # now works
```

Note: `/etc` is always writable -- no special command needed for config files there.

## References

- [Podman 5.6 Rosetta blog post](https://blog.podman.io/2025/08/podman-5-6-released-rosetta-status-update/)
- [Podman Desktop Rosetta docs](https://podman-desktop.io/docs/podman/rosetta)
- [containers/podman#28181](https://github.com/containers/podman/issues/28181) -- Rosetta binfmt
  registration silently fails despite config showing `true`
- [containers/podman-machine-os#212](https://github.com/containers/podman-machine-os/issues/212) --
  Re-enable Rosetta discussion
