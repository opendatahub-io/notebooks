# Elyra KFP `bootstrapper.py` (v4.3.1)

This directory vendors a single file from [opendatahub-io/elyra](https://github.com/opendatahub-io/elyra) tag **v4.3.1**:

- **`bootstrapper.py`** — runtime helper used when Elyra executes Kubeflow Pipelines on pipeline runtime images. The Dockerfiles under `runtimes/*/ubi9-python-3.12/` copy it to `/opt/app-root/bin/utils/bootstrapper.py` (see `COPY … prefetch-input/elyra-v4.3.1/elyra/kfp/bootstrapper.py`).

Keeping the script in-repo avoids fetching it at image build time (no `curl` and no generic cachi2 URL for this file). To refresh after an Elyra release, replace `bootstrapper.py` with the same path from the new tag and bump the `elyra-v4.3.1` directory name if the version changes.

Upstream source: `https://raw.githubusercontent.com/opendatahub-io/elyra/refs/tags/v4.3.1/elyra/kfp/bootstrapper.py`
