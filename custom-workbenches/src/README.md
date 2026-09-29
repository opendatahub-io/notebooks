# Template source (`src/`)

Reusable template copied by `../interactive-image-builder.sh` into a sibling
folder (for example `../universal-minimal-cpu/` or `../my-pytorch-cuda/`).

| Path | Role |
|------|------|
| `Containerfile` | Universal workbench/runtime image (dual labels) |
| `pyproject.toml` | JupyterLab + Elyra runtime deps (unpinned) |
| `build-args/{cpu,cuda,rocm}.conf` | Default `BASE_IMAGE` / `INDEX_URL` |
| `collections/` | TrustyAI, LLM Compressor, PyTorch package sets + constraints |
| `bin/entrypoint.sh` | Jupyter by default; `runtime` / `WORKBENCH_MODE` for local probes |
| `bin/validate-universal.sh` | Local §1 dual-mode checks |
| `bin/utils/requirements-elyra.txt` | Blank escape hatch (skip Elyra curl) |
| `imagestream.yaml.in` | Dual `notebook-image` + `runtime-image` labels |
| `lib/` | Wizard helpers (not copied into customer images) |
| `defaults/` | Base image and index URL catalogs |

Do **not** run `make build RECIPE=src`.

**Build / push / `podman run` examples** for universal Minimal CPU, PyTorch CUDA,
PyTorch ROCm, TrustyAI CPU, and LLM Compressor CUDA live in the parent
[README.md](../README.md).
