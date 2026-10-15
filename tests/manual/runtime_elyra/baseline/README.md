# Baseline runtime Elyra smoke pipeline

Stdlib-only Elyra pipeline for validating **runtime-baseline** images and the dual-mode
**Universal Jupyter** workbench/runtime image on a cluster.
Use this instead of the [iris sample](https://github.com/harshad16/data-science-pipeline-example):
these lean images ship Elyra/Kale execution deps only (no pandas, scikit-learn, or PyTorch).

## What it exercises

| Step | Script | Output artifact | Validates |
|------|--------|-----------------|-----------|
| 1 | `generate_records.py` | `raw_records` (CSV) | Python execution, artifact write |
| 2 | `summarize_records.py` | `summary` (JSON) | Upstream artifact mount, stdlib `statistics` |
| 3 | `validate_report.py` | `validation_report` (JSON) | Final artifact write, non-zero exit on failure |

Pipeline parameters (optional):

- `record_count` (default `10`) — passed as env var to the first node
- `random_seed` (default `42`) — passed as env var to the first node

## Prerequisites

1. **Pipeline server (DSPA)** configured and **Ready** in your project.
   See [../README.md](../README.md) for the general Elyra setup flow.
2. **S3-compatible storage** reachable by the pipeline server (AWS, MinIO, or DSPA-managed MinIO).
   If using DSPA-managed MinIO, ensure the S3 secret exposes both Elyra key styles when needed:
   `accesskey`/`secretkey` **and** `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.
3. **Elyra-enabled workbench** in the same project (Jupyter Baseline, Universal Jupyter, or
   datascience). Restart the workbench after creating the pipeline server so the **Runtime**
   dropdown is populated.
4. **Runtime ImageStream** available in the cluster:
   - Baseline: e.g. `runtime-baseline` in `redhat-ods-applications`
   - Universal: `jupyter-universal-notebook` (same digest as the workbench; dual-mode entrypoint)

## Run the pipeline

1. Open your workbench in JupyterLab.
2. Copy this folder into the workbench workspace (Git clone, upload, or `oc rsync`).
3. In the file browser, open `baseline-elyra.pipeline`.
4. For **each** node (`generate-records`, `summarize-records`, `validate-report`):
   - Select the node.
   - Set **Runtime Image** to the image under test (see below).
5. Click **Run pipeline** (play icon).
6. In the run dialog:
   - **Runtime**: choose your project's pipeline server (not empty).
   - Name the run (e.g. `baseline-smoke-1` or `universal-smoke-1`).
7. Confirm all three steps reach **Succeeded** in Experiments → Experiments and runs.

### Runtime image selection

| Image under test | Runtime Image dropdown (typical label) |
|------------------|----------------------------------------|
| runtime-baseline | **Runtime \| Baseline \| CPU \| Python 3.12 \| Latest** (or BYON tag) |
| jupyter-universal | **Universal Jupyter** / `jupyter-universal-notebook` (or BYON pointing at the same digest used as the workbench) |

## Universal Jupyter as runtime

Universal Jupyter uses `entrypoint-universal.sh`: pipeline pods override the command (Elyra
`bootstrapper.py`) or pass `runtime` as the first arg. Workbench and runtime must be the
**same image digest** for RHAIENG-7730 AC coverage.

1. Deploy or select a workbench from the `jupyter-universal-notebook` imagestream.
2. Ensure the Universal image is also selectable as an Elyra **Runtime Image** (imagestream
   annotation / runtime-images ConfigMap — same digest as the workbench).
3. Run this stdlib pipeline with every node set to that Universal runtime image.
4. Attach the succeeded run (UI screenshot or `oc` logs) to
   [RHAIENG-7730](https://redhat.atlassian.net/browse/RHAIENG-7730).

Image build and dual-mode docs:
[`jupyter/universal/ubi9-python-3.12/README.md`](../../../../jupyter/universal/ubi9-python-3.12/README.md).

### Expected result

- Run status: **Succeeded**
- Final artifact `validation_report` contains `"status": "PASS"`
- No `ModuleNotFoundError` or `pip install` in pod logs

### Common failures

| Symptom | Likely cause |
|---------|----------------|
| Empty **Runtime** dropdown | No DSPA in project, or workbench started before DSPA was Ready — restart workbench |
| `CreateContainerConfigError` on S3 env vars | S3 secret missing `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| `ModuleNotFoundError: pandas` (or sklearn) | Wrong runtime image — iris/datascience stacks are not baseline/universal-compatible |
| Workbench starts Jupyter instead of pipeline | Command not overridden — Elyra must set the container command to bootstrapper (or `runtime`) |
| Pod pruned / not found in UI | Misleading KFP node id; check the actual pod name in OpenShift **Workloads → Pods** |

## Local script sanity check (optional)

From a Python 3.12 interpreter (no cluster required):

```bash
cd tests/manual/runtime_elyra/baseline
python3.12 generate_records.py
python3.12 summarize_records.py
python3.12 validate_report.py
cat validation_report
```

## Related docs

- [Runtime Elyra testing (datascience / iris)](../README.md)
- [Runtime baseline image](../../../../runtimes/baseline/ubi9-python-3.12/)
- [Jupyter baseline workbench](../../../../jupyter/baseline/ubi9-python-3.12/)
- [Jupyter universal workbench / runtime](../../../../jupyter/universal/ubi9-python-3.12/)
