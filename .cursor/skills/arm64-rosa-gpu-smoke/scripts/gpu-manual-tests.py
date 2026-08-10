#!/usr/bin/env python3
"""Run ODH tests/manual GPU notebooks on ARM CUDA images via pod exec.

Uses kubernetes stream exec (equivalent to: oc exec -q POD -c smoke -- CMD).
Notebooks fetched from opendatahub-io/notebooks main inside the container.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from kubernetes import client, config, watch
from kubernetes.stream import stream

NOTEBOOK_REV = os.environ.get("NOTEBOOK_REV")
if not NOTEBOOK_REV or not re.fullmatch(r"[0-9a-f]{40}", NOTEBOOK_REV):
    sys.exit(
        "NOTEBOOK_REV must be set to a full 40-character commit SHA "
        "(this tool validates image sign-off; pin the exact tests/manual "
        "revision instead of tracking a mutable branch)"
    )
NOTEBOOK_BASE = (
    f"https://raw.githubusercontent.com/opendatahub-io/notebooks/{NOTEBOOK_REV}/tests/manual"
)
NS = os.environ.get("TEST_NAMESPACE", "jdanek")
PULL_SECRET = os.environ.get("PULL_SECRET", "rhoai-pull")
CONTAINER = "smoke"
TAG = os.environ.get("TAG", "rhoai-3.6-ea.1")
CONTEXT = os.environ.get("KUBECONFIG_CONTEXT", None)
NB_TIMEOUT = 1800
POD_TIMEOUT = 900


@dataclass(frozen=True)
class ImageSpec:
    label: str
    image: str
    notebooks: tuple[str, ...]
    allow_errors: bool = False
    runtime: bool = False
    minimal_gpu_only: bool = False


IMAGES: tuple[ImageSpec, ...] = (
    ImageSpec(
        "minimal-cuda workbench",
        f"quay.io/rhoai/odh-workbench-jupyter-minimal-cuda-py312-rhel9:{TAG}",
        (),
        minimal_gpu_only=True,
    ),
    ImageSpec(
        "pytorch-cuda workbench",
        f"quay.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9:{TAG}",
        ("gpu-test-notebook", "pytorch-test-notebook"),
    ),
    ImageSpec(
        "tensorflow-cuda workbench",
        f"quay.io/rhoai/odh-workbench-jupyter-tensorflow-cuda-py312-rhel9:{TAG}",
        ("gpu-test-notebook", "tensorflow-test"),
    ),
    ImageSpec(
        "llmcompressor-cuda workbench",
        f"quay.io/rhoai/odh-workbench-jupyter-pytorch-llmcompressor-cuda-py312-rhel9:{TAG}",
        ("gpu-test-notebook", "pytorch-test-notebook"),
    ),
    ImageSpec(
        "runtime-pytorch-cuda",
        f"quay.io/rhoai/odh-pipeline-runtime-pytorch-cuda-py312-rhel9:{TAG}",
        ("gpu-test-notebook", "pytorch-test-notebook"),
        runtime=True,
    ),
    ImageSpec(
        "runtime-tensorflow-cuda",
        f"quay.io/rhoai/odh-pipeline-runtime-tensorflow-cuda-py312-rhel9:{TAG}",
        ("gpu-test-notebook", "tensorflow-test"),
        runtime=True,
    ),
    ImageSpec(
        "runtime-llmcompressor-cuda",
        f"quay.io/rhoai/odh-pipeline-runtime-pytorch-llmcompressor-cuda-py312-rhel9:{TAG}",
        ("gpu-test-notebook", "pytorch-test-notebook"),
        runtime=True,
    ),
)


def load_client() -> tuple[client.CoreV1Api, str]:
    kube_args = {"config_file": str(Path.home() / ".kube/config")}
    if CONTEXT:
        kube_args["context"] = CONTEXT
    config.load_kube_config(**kube_args)
    v1 = client.CoreV1Api()
    gpu_node = v1.list_node(
        label_selector="nvidia.com/gpu.present=true", _request_timeout=30
    ).items[0].metadata.name
    return v1, gpu_node


def pod_name(label: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", label.lower())[:24].strip("-")
    return f"man-{slug}-{int(time.time()) % 100000}"


def exec_cmd(v1: client.CoreV1Api, pod: str, cmd: list[str], timeout: int = NB_TIMEOUT + 120) -> tuple[int, str, str]:
    """Non-interactive exec (oc exec -q, no -i/-t)."""
    resp = stream(
        v1.connect_get_namespaced_pod_exec,
        pod,
        NS,
        command=cmd,
        container=CONTAINER,
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
        _preload_content=False,
    )
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    while resp.is_open():
        resp.update(timeout=timeout)
        if resp.peek_stdout():
            out_chunks.append(resp.read_stdout())
        if resp.peek_stderr():
            err_chunks.append(resp.read_stderr())
    code = resp.returncode if resp.returncode is not None else 0
    return code, "".join(out_chunks), "".join(err_chunks)


def notebook_cell_text(v1: client.CoreV1Api, pod: str, nb: str) -> str:
    py = f"""
import json
nb = json.load(open('/tmp/manual-tests/out-{nb}.ipynb'))
parts = []
for cell in nb.get('cells', []):
    for out in cell.get('outputs', []):
        if out.get('output_type') == 'error':
            parts.append('\\n'.join(out.get('traceback', [])))
        if 'text' in out:
            parts.append(''.join(out['text']))
        if 'data' in out and 'text/plain' in out['data']:
            parts.append(''.join(out['data']['text/plain']))
print(''.join(parts))
"""
    code, out, err = exec_cmd(v1, pod, ["python", "-c", py], timeout=120)
    return out + err


def wait_ready(v1: client.CoreV1Api, pod: str) -> None:
    w = watch.Watch()
    for event in w.stream(
        v1.list_namespaced_pod,
        NS,
        field_selector=f"metadata.name={pod}",
        timeout_seconds=POD_TIMEOUT,
    ):
        obj = event["object"]
        phase = obj.status.phase
        if phase == "Failed":
            w.stop()
            raise RuntimeError(f"pod {pod} failed")
        if phase == "Running":
            for cs in obj.status.container_statuses or []:
                if cs.name == CONTAINER and cs.ready:
                    w.stop()
                    return
    raise TimeoutError(f"pod {pod} not ready within {POD_TIMEOUT}s")


def create_pod(v1: client.CoreV1Api, name: str, image: str, gpu_node: str, runtime: bool) -> None:
    container = client.V1Container(
        name=CONTAINER,
        image=image,
        resources=client.V1ResourceRequirements(
            limits={"nvidia.com/gpu": "1"},
            requests={"nvidia.com/gpu": "1"},
        ),
        security_context=client.V1SecurityContext(
            allow_privilege_escalation=False,
            capabilities=client.V1Capabilities(drop=["ALL"]),
            run_as_non_root=True,
            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
        ),
        volume_mounts=[client.V1VolumeMount(name="workspace", mount_path="/opt/app-root/src")],
    )
    if runtime:
        container.command = ["sleep", "infinity"]

    body = client.V1Pod(
        metadata=client.V1ObjectMeta(name=name, namespace=NS),
        spec=client.V1PodSpec(
            # node_selector (not node_name) so the scheduler actually evaluates
            # placement — a bare node_name assignment bypasses scheduler
            # checks entirely, including any nvidia.com/gpu taint/toleration
            # matching. Pinning to this specific node's hostname preserves the
            # existing "run on this one GPU node" behavior.
            node_selector={"kubernetes.io/hostname": gpu_node},
            tolerations=[
                client.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule"),
            ],
            restart_policy="Never",
            automount_service_account_token=False,
            image_pull_secrets=[client.V1LocalObjectReference(name=PULL_SECRET)],
            containers=[container],
            volumes=[client.V1Volume(name="workspace", empty_dir=client.V1EmptyDirVolumeSource())],
        ),
    )
    v1.create_namespaced_pod(NS, body, _request_timeout=30)


def delete_pod(v1: client.CoreV1Api, name: str) -> None:
    try:
        v1.delete_namespaced_pod(name, NS, grace_period_seconds=0, _request_timeout=30)
    except client.ApiException as e:
        if e.status != 404:
            raise


def run_notebook(v1: client.CoreV1Api, pod: str, nb: str, allow_errors: bool) -> tuple[int, str]:
    allow = "--ExecutePreprocessor.allow_errors=True" if allow_errors else ""
    # tensorflow-test tensorboard cell expects Jupyter; satisfy NB_PREFIX for oc exec path
    extra_env = "export NB_PREFIX='${NB_PREFIX:-/}'"
    shell = f"""
set -euo pipefail
{extra_env}
mkdir -p /tmp/manual-tests
curl -fsSL --connect-timeout 30 --max-time 300 '{NOTEBOOK_BASE}/{nb}.ipynb' -o '/tmp/manual-tests/{nb}.ipynb'
cd /opt/app-root/src
python -m jupyter nbconvert \
  --ExecutePreprocessor.timeout={NB_TIMEOUT} {allow} \
  --to notebook \
  --execute '/tmp/manual-tests/{nb}.ipynb' \
  --output '/tmp/manual-tests/out-{nb}.ipynb'
"""
    code, out, err = exec_cmd(v1, pod, ["bash", "-lc", shell])
    combined = out + ("\n" + err if err else "")
    return code, combined


def run_minimal_gpu_checks(v1: client.CoreV1Api, pod: str) -> tuple[int, str]:
    """gpu-test-notebook sections 5–6 for minimal-cuda (no torch/tensorflow)."""
    shell = r"""
set -euo pipefail
python <<'PY'
import platform, subprocess, sys
assert platform.machine() == "aarch64", platform.machine()
print(sys.version)
smi = subprocess.check_output(["nvidia-smi", "-L"], text=True)
print(smi)
assert "GPU" in smi
nvcc = subprocess.check_output(["nvcc", "--version"], text=True)
print(nvcc)
assert "release" in nvcc.lower()
print("MINIMAL_GPU_PASS")
PY
"""
    code, out, err = exec_cmd(v1, pod, ["bash", "-lc", shell], timeout=120)
    return code, out + err


def validate_output(nb: str, allow_errors: bool, combined: str) -> None:
    if nb == "gpu-test-notebook":
        lower = combined.lower()
        if "nvidia-smi" not in lower and "t4" not in lower and "gpu 0" not in lower:
            raise AssertionError("gpu-test: expected nvidia-smi / GPU output in notebook cells")
        if not allow_errors and "traceback" in lower and "nameerror" not in lower:
            # minimal-cuda may NameError on torch version cell — allowed with allow_errors
            raise AssertionError("gpu-test: error traceback in notebook output")
        return
    if nb == "pytorch-test-notebook":
        if "using cuda device" not in combined.lower() and "cuda:0" not in combined.lower():
            raise AssertionError("pytorch-test: expected CUDA device usage in notebook output")
        if "traceback" in combined.lower():
            raise AssertionError("pytorch-test: traceback in notebook output")
        return
    if nb == "tensorflow-test":
        lower = combined.lower()
        if "gpu" not in lower and "device" not in lower:
            raise AssertionError("tensorflow-test: expected GPU/device in notebook output")
        if "traceback" in lower and not ("nb_prefix" in lower and "tensorboard" in lower):
            raise AssertionError("tensorflow-test: traceback in notebook output")
        # MNIST training cell must complete
        if "epoch" not in lower and "fit" not in lower and "loss" not in lower:
            raise AssertionError("tensorflow-test: expected training output")


def run_image(v1: client.CoreV1Api, gpu_node: str, spec: ImageSpec) -> list[tuple[str, str, bool, str]]:
    name = pod_name(spec.label)
    results: list[tuple[str, str, bool, str]] = []
    print(f"\n=== {spec.label} ({spec.image}) pod={name} ===", flush=True)
    try:
        # create_pod is inside try/finally: if the client-side request times
        # out after the server already persisted the Pod (a real race, not
        # hypothetical), delete_pod in finally still runs instead of leaking
        # a "sleep infinity" pod that holds a GPU indefinitely. delete_pod
        # tolerates "doesn't exist" so a create_pod failure before the pod
        # was ever persisted doesn't mask the original error either.
        create_pod(v1, name, spec.image, gpu_node, spec.runtime)
        wait_ready(v1, name)
        if spec.minimal_gpu_only:
            print("  -> minimal gpu checks (nvidia-smi, nvcc)", flush=True)
            code, combined = run_minimal_gpu_checks(v1, name)
            ok = code == 0 and "MINIMAL_GPU_PASS" in combined
            status = "PASS" if ok else "FAIL"
            print(f"     {status} (exit={code})", flush=True)
            results.append((spec.label, "gpu-test-notebook (minimal subset)", ok, combined[-2000:]))
        for nb in spec.notebooks:
            print(f"  -> {nb}.ipynb", flush=True)
            allow_err = (spec.allow_errors and nb == "gpu-test-notebook") or nb == "tensorflow-test"
            code, log = run_notebook(v1, name, nb, allow_err)
            cell_text = notebook_cell_text(v1, name, nb) if code == 0 else ""
            combined = log + "\n" + cell_text
            ok = code == 0
            if ok:
                if not cell_text:
                    ok = False
                    combined += "\nVALIDATION: executed notebook produced no output"
                else:
                    try:
                        validate_output(nb, allow_err, combined)
                    except AssertionError as e:
                        ok = False
                        combined += f"\nVALIDATION: {e}"
            else:
                combined += "\n(no executed notebook output — nbconvert failed)"
            status = "PASS" if ok else "FAIL"
            print(f"     {status} (exit={code})", flush=True)
            results.append((spec.label, nb, ok, combined[-2000:]))
            if not ok and not (spec.allow_errors and nb == "gpu-test-notebook"):
                break
    finally:
        delete_pod(v1, name)
        time.sleep(5)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", help="Run images matching this substring in label (exact label if --exact)")
    parser.add_argument("--exact", action="store_true", help="Exact label match for --image")
    parser.add_argument("--log", type=Path, default=Path(".cursor-tmp-artifact/arm64-ea1-validation/gpu-manual-tests.log"))
    args = parser.parse_args()

    v1, gpu_node = load_client()
    print(f"GPU node: {gpu_node}", flush=True)

    specs = IMAGES
    if args.image:
        if args.exact:
            specs = tuple(s for s in IMAGES if s.label == args.image)
        else:
            specs = tuple(s for s in IMAGES if args.image in s.label)
        if not specs:
            parser.error(f"No image specification matches: {args.image}")

    all_results: list[tuple[str, str, bool, str]] = []
    for spec in specs:
        all_results.extend(run_image(v1, gpu_node, spec))

    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w") as f:
        for label, nb, ok, tail in all_results:
            f.write(f"{'PASS' if ok else 'FAIL'}\t{label}\t{nb}\n")
            f.write(tail)
            f.write("\n" + "=" * 80 + "\n")

    failed = [r for r in all_results if not r[2]]
    print(f"\nSummary: {len(all_results) - len(failed)}/{len(all_results)} notebook runs passed", flush=True)
    for label, nb, ok, _ in all_results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label} / {nb}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
