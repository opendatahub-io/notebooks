# Test Plan: NVIDIA GPU Operator Version Change (RHAIENG-3308)

Verify that a workbench remains functional after changing the NVIDIA GPU driver version on an OpenShift AI cluster.

## Phase 1 — Build and deploy the workbench image

Build the data-science workbench image and push it to a staging registry:

```bash
gmake jupyter-datascience-ubi9-python-3.12 \
  IMAGE_REGISTRY=quay.io/mtchoumi-aaet/workbench-images \
  RELEASE=normal \
  PUSH_IMAGES=yes
```

Import the image into OpenShift AI:

1. Open the OpenShift AI dashboard.
2. Navigate to **Settings → Environment setup → Workbench images**.
3. Click **Import new image** and provide the registry URL from the build step above.

## Phase 2 — Establish a baseline (pre-migration)

Record the current driver version and confirm the GPU works before changing anything.

1. Check the driver version on the GPU node:

```bash
oc describe node <gpu-node> | grep cuda.driver
```

2. Open the validation notebook in the workbench and run it end-to-end.
   The notebook must detect the GPU and execute without errors — this is the "before" snapshot.

## Phase 3 — Change the driver version

Patch `ClusterPolicy` to point at the target driver version (e.g. `570.158.01`):

```bash
oc patch clusterpolicy gpu-cluster-policy --type merge -p '{
  "spec": {
    "driver": {
      "repository": "nvcr.io/nvidia",
      "image": "driver",
      "version": "570.158.01"
    }
  }
}'
```

Delete the driver daemonset pods so the operator rolls out the new version:

```bash
oc delete pod -n nvidia-gpu-operator -l app=nvidia-driver-daemonset-<rhel-tag>
```

Replace `<rhel-tag>` with the tag matching the node OS (e.g. `9.6.20251203-0`).

Wait for the replacement pods to reach `Running` before proceeding:

```bash
oc get pods -n nvidia-gpu-operator -l app=nvidia-driver-daemonset-<rhel-tag> -w
```

## Phase 4 — Verify the new driver (post-migration)

1. Confirm the node now reports the target driver:

```bash
oc describe node <gpu-node> | grep cuda.driver
# expected: cuda.driver.major=570, cuda.driver.minor=158, etc.
```

2. Re-run the same validation notebook.
   **Pass criteria:** the notebook detects the GPU and completes successfully under the new driver version.
