# NVIDIA Driver Compilation on ROSA (DTK vs Precompiled)

Validated on RHOAI ARM64 CUDA sign-off cluster **`jd-arm64-ea1`** (ROSA HCP, OCP **4.21.0**, kernel `5.14.0-570.78.1.el9_6.aarch64`, GPU Operator **v25.3.4**, driver **580.82.07**).

## Default behavior (what happens today)

With the stock `ClusterPolicy` from GPU Operator CSV `alm-examples`:

- `spec.driver.usePrecompiled` is **false** (unset)
- `spec.operator.use_ocp_driver_toolkit` is **true**

The GPU Operator deploys a driver daemonset pod with two containers:

1. **nvidia-driver-ctr** — copies driver sources, loads modules, starts NVIDIA services
2. **openshift-driver-toolkit-ctr** — compiles kernel modules against the node's RHCOS kernel via Driver Toolkit (DTK)

Compilation runs **on every GPU node** for each distinct kernel version. There is no cluster-wide registry cache of built modules on this path.

### Startup cascade (normal)

Other GPU Operator pods stay `Init:0/1` or `Pending` until the driver pod is Ready:

```
nvidia-driver-daemonset (compiling)
  → nvidia-container-toolkit-daemonset
    → nvidia-device-plugin-daemonset
      → gpu-feature-discovery
        → nvidia-operator-validator
```

Only after `nvidia.com/gpu` appears in node allocatable can Phase 3 GPU smoke tests run.

### Observed timings: g5g.xlarge vs g5g.2xlarge

Same kernel and driver branch; only instance size differed.

| Signal | `g5g.xlarge` (failed path) | `g5g.2xlarge` (success path) |
|--------|---------------------------|------------------------------|
| Time to driver **2/2 Ready** | **70+ min**, still 1/2 | **~30 min** |
| Last log line | Stuck on `make -s -j … nv-linux.o nv-modeset-linux.o` (40+ min unchanged) | gcc warnings (e.g. `os_dbg_breakpoint` aarch64), then progress |
| Node CPU during compile | ~4000m (**114%** of 3500m allocatable) | ~4000m (**63%** of 8 vCPU) |
| DTK pod RAM | **~6.3 GiB** | **~1–4 GiB** during compile, ~1 GiB after Ready |
| Node memory | **104%**, `MemoryPressure=True` | **26–29%**, no memory pressure |
| `oc exec` into DTK | Hangs | Works |
| After Ready | — | `nvidia-cuda-validator` Completed, `nvidia.com/gpu: 1` |

`make -s -j` produces little log output while gcc runs — on **xlarge**, long silence + memory pressure usually means **stall**, not “almost done”. On **2xlarge**, occasional gcc warnings are a good sign compile is moving.

**Quick mitigations (still compile on-node):**

- **Default to `g5g.2xlarge`** for any G5g pool that will run DTK on first install
- If already on xlarge: create new `g5g.2xlarge` machine pool, delete old pool — instance type cannot be edited in place (see [SKILL.md](SKILL.md#resize-gpu-pool-instance-type-is-immutable))
- Wait with extended timeout: `oc wait … --timeout=1800s`

**Not a mitigation:** switching to precompiled mid-flight on the same cluster — you must build and publish the image first.

## Is on-node compilation inevitable?

**No**, but it is the default. Alternatives:

| Path | Compile on each new GPU node? | Who builds? |
|------|-------------------------------|-------------|
| DTK sidecar (default) | Yes, per node × kernel | The node |
| Precompiled driver image | No — load prebuilt `.ko` from registry | You, once per (driver, kernel, OCP) |
| Entitled builds | Deprecated on OCP 4.10+ | Do not use |

### On-node caching (limited)

- **New nodes, same kernel:** default path still compiles again on each node.
- **Same node, driver pod restart:** GPU Operator **v26.3.0+** can reuse loaded kernel modules if driver version/config unchanged (seconds vs minutes). **v25.3.x** (current certified channel) does not have this improvement.

## Precompiled drivers (“build once, pull on nodes”)

NVIDIA documents this for OpenShift as **Technology Preview**:

- [Precompiled Drivers for RHCOS](https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/gpu-operator-with-precompiled-drivers.html)

### Key facts

1. **NVIDIA does not publish precompiled driver images for OpenShift.** You build and host them (e.g. `quay.io/<org>/nvidia-gpu-driver:…`).
2. Red Hat ships **Driver Toolkit** images (build environment), not prebuilt NVIDIA drivers.
3. Red Hat measured roughly **2–3 minutes** saved per GPU node vs in-cluster compile when using precompiled images (bigger win when autoscaling many G5g nodes).

### Enable in ClusterPolicy

```yaml
spec:
  driver:
    usePrecompiled: true
    repository: quay.io/<your-org>
    image: nvidia-gpu-driver
    version: "580"   # driver branch; must match operator expectations
```

Driver daemonset pod names include the **kernel version** (e.g. `nvidia-driver-daemonset-5.14.0-570.78.1.el9_6.aarch64-…`) instead of the DTK-style `openshift-driver-toolkit` sidecar layout.

### Building the image

Procedure (summarized from NVIDIA docs):

```bash
git clone https://github.com/NVIDIA/gpu-driver-container.git
cd gpu-driver-container/rhel9/precompiled   # RHEL 9 / RHCOS 4.13+

export OPENSHIFT_VERSION="4.21.0"
export TARGET_ARCH="aarch64"              # not arm64

# DTK image for this OCP release + arch
export DRIVER_TOOLKIT_IMAGE=$(oc adm release info \
  --image-for=driver-toolkit \
  quay.io/openshift-release-dev/ocp-release:${OPENSHIFT_VERSION}-${TARGET_ARCH})

export KERNEL_VERSION=$(podman run --rm -ti ${DRIVER_TOOLKIT_IMAGE} \
  cat /etc/driver-toolkit-release.json | jq -r '.KERNEL_VERSION')

export DRIVER_VERSION=580.82.07             # match ClusterPolicy / operator
export CUDA_VERSION=12.x.x                # base image tag selection
export OS_TAG=...                         # see below

make image image-push
```

**Image tag format** must encode driver, kernel, and OS, e.g.:

`580.82.07-5.14.0-570.78.1.el9_6.aarch64-<os-tag>`

**OS tag suffix changed at OCP 4.19:**

- Before 4.19: `rhcos4.xx` (e.g. `rhcos4.17`)
- OCP 4.19+: `rhel9.6` style (verify against GPU Operator 25.3.4 OpenShift docs for your exact release)

**aarch64 page size:** Some RHEL 9 aarch64 kernels use a `+64k` suffix in tags. Match the kernel from DTK / node labels, not assumptions from amd64 builds.

### Limitations

- Technology Preview — not for production
- No **vGPU** or **GPUDirect Storage (GDS)**
- Limited NVIDIA support for custom images
- **Rebuild** when RHCOS kernel or driver branch changes (every node OS update)

## When to use which path

| Scenario | Recommendation |
|----------|----------------|
| One-off smoke test on a single G5g node | **`g5g.2xlarge`** — xlarge DTK compile is unreliable |
| Already created `g5g.xlarge` pool and compile stalled | New `gpu-arm2` pool at 2xlarge, delete old pool (~30 min recompile) |
| Repeated ARM CUDA sign-off / autoscaling G5g pools | Invest in precompiled images per (OCP, kernel, driver branch) |
| Ephemeral dev clusters torn down daily | Precompiled saves wall-clock on every new GPU node |

## References

- [ROSA HCP provisioning skill](SKILL.md) — cluster create, G5g pool, GPU Operator CLI install
- [ARM64 CUDA smoke skill](../arm64-rosa-gpu-smoke/SKILL.md) — Phases 3a–3b (Pod smoke + manual notebooks) after `nvidia.com/gpu` is allocatable
- [Red Hat: precompiled drivers and autoscaling](https://www.redhat.com/en/blog/how-precompiled-drivers-improve-nvidia-gpu-autoscaling-on-red-hat-openshift)
- [OCP 4.21 Driver Toolkit](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html-single/specialized_hardware_and_driver_enablement/index)
