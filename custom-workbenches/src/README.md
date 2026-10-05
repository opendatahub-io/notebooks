# Template source (`src/`)

Reusable template copied by `../interactive-image-builder.sh` into a sibling
folder (for example `../my-pytorch-cuda/`).

| Path | Role |
|------|------|
| `Containerfile` | Universal workbench/runtime image |
| `pyproject.toml` | Minimal Jupyter baseline (unpinned) |
| `build-args/{cpu,cuda,rocm}.conf` | Default `BASE_IMAGE` / `INDEX_URL` |
| `collections/` | TrustyAI, LLM Compressor, PyTorch package sets + constraints |
| `bin/entrypoint.sh` | Jupyter by default; `runtime` → Elyra bootstrapper |
| `lib/` | Wizard helpers (not copied into customer images) |
| `defaults/` | Base image and index URL catalogs |

Do **not** run `make build RECIPE=src`.

**Build / push / `podman run` examples** for PyTorch CUDA, PyTorch ROCm, TrustyAI
CPU, and LLM Compressor CUDA live in the parent [README.md](../README.md).
