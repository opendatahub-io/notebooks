# Baseline runtime Elyra smoke pipeline

Stdlib-only Elyra pipeline for validating **runtime-baseline** images on a cluster.
Use this instead of the [iris sample](https://github.com/harshad16/data-science-pipeline-example):
baseline runtimes ship Elyra/Kale execution deps only (no pandas, scikit-learn, or PyTorch).

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
3. **Jupyter Baseline workbench** (or any Elyra-enabled workbench) in the same project.
   Restart the workbench after creating the pipeline server so the **Runtime** dropdown is populated.
4. **Runtime-baseline ImageStream** available in the cluster (e.g. `runtime-baseline` in
   `redhat-ods-applications`).

## Run the pipeline

1. Open your baseline workbench in JupyterLab.
2. Copy this folder into the workbench workspace (Git clone, upload, or `oc rsync`).
3. In the file browser, open `baseline-elyra.pipeline`.
4. For **each** node (`generate-records`, `summarize-records`, `validate-report`):
   - Select the node.
   - Set **Runtime Image** to **Runtime | Baseline | CPU | Python 3.12 | Latest** (or your BYON tag).
5. Click **Run pipeline** (play icon).
6. In the run dialog:
   - **Runtime**: choose your project's pipeline server (not empty).
   - Name the run (e.g. `baseline-smoke-1`).
7. Confirm all three steps reach **Succeeded** in Experiments → Experiments and runs.

### Expected result

- Run status: **Succeeded**
- Final artifact `validation_report` contains `"status": "PASS"`
- No `ModuleNotFoundError` or `pip install` in pod logs

### Common failures

| Symptom | Likely cause |
|---------|----------------|
| Empty **Runtime** dropdown | No DSPA in project, or workbench started before DSPA was Ready — restart workbench |
| `CreateContainerConfigError` on S3 env vars | S3 secret missing `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| `ModuleNotFoundError: pandas` (or sklearn) | Wrong runtime image — iris/datascience stacks are not baseline-compatible |
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
