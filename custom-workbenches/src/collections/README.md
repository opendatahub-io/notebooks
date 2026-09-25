# Use-case Python package collections (RHAIENG-7241 §3)

Curated package sets for the **Red Hat / AIPCC Python index**, used instead of
shipping specialized OOTB images.

## ABI rule: one collection per `site-packages`

PyTorch and TrustyAI often **cannot share one environment**. Example:

| Collection | Typical shared-lib ceiling |
|------------|----------------------------|
| TrustyAI | `numpy>=1.26,<2.1` `pandas>=2.0,<3` |
| PyTorch / LLM Compressor | `numpy>=2.0` `pandas>=2.2` |

Those ranges are **collection constraints** (`constraints` in `collection.toml`).
`pip`/`uv` install with `-c constraints.txt` so “latest” still means **latest
inside that ABI**, not globally latest.

If two collections declare **different specs for the same package**, generation
fails. Do **not** merge them into one image.

### What to do instead

1. **Two images** — one TrustyAI workbench, one PyTorch/LLM Compressor workbench (preferred).
2. **Isolated venv** — keep the image on one collection; install the other into
   a venv on the PVC (`python -m venv ~/venvs/other && pip install -c …`). Do not
   mix AIPCC-built and PyPI-built binary wheels in the same venv unless you have
   validated that combination (RHAIENG-7241 §4).

`conflicts_with` in `collection.toml` encodes known-bad pairs (TrustyAI vs PyTorch /
LLM Compressor).

## Workflow

1. **Discover** — `make collections`
2. **Select** — wizard: one stack only
3. **Install** — `make build` uses `requirements.txt` + `constraints.txt`
4. **Validate** — `make validate RECIPE=<folder>`
