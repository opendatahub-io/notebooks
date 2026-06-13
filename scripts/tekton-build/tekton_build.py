#!/usr/bin/env python3
"""Drive local/GHA container builds from .tekton/*-pull-request.yaml PipelineRuns."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1) from exc

REPO_ROOT = Path(__file__).resolve().parents[2]
TEKTON_DIR = REPO_ROOT / ".tekton"
PREFETCH_SCRIPT = REPO_ROOT / "scripts/tekton-build/prefetch-hermeto.sh"
BUILD_SCRIPT = REPO_ROOT / "scripts/tekton-build/build-konflux.sh"
HERMETO_CONFIG = REPO_ROOT / "scripts/tekton-build/hermeto-config.yaml"
PYPI_SIMPLE_INDEX = "https://pypi.org/simple"
DEFAULT_PIP_BINARY = {
    "packages": ":all:",
    "os": "linux",
    "py_impl": "cp",
    "py_version": 312,
}
# GHA cannot prefetch/build some Konflux MPC platforms: lockfiles / RHOAI omit wheels.
GHA_EXCLUDED_PLATFORMS_BY_FLAVOR: dict[str, frozenset[str]] = {
    "cuda": frozenset({"linux/ppc64le", "linux/s390x"}),
}
PATH_CHANGED_RE = re.compile(r'"([^"]+)"\.pathChanged\(\)')
PLATFORM_ARCH = {
    "amd64": "x86_64",
    "arm64": "aarch64",
    "ppc64le": "ppc64le",
    "s390x": "s390x",
}
PREFETCH_BINARY_ARCH = PLATFORM_ARCH
# GHA runner labels (same mapping as build-notebooks-TEMPLATE.yaml).
PLATFORM_RUNNERS = {
    "linux/amd64": "ubuntu-24.04",
    "linux/arm64": "ubuntu-24.04-arm",
    "linux/ppc64le": "ubuntu-24.04",
    "linux/s390x": "ubuntu-24.04",
}
QEMU_PLATFORMS = frozenset({"linux/ppc64le", "linux/s390x"})


@dataclass
class PipelineRun:
    path: Path
    name: str
    component: str
    dockerfile: str
    path_context: str
    build_args_file: str
    build_args: list[str]
    hermetic: bool
    prefetch_input: list[dict]
    build_platforms: list[str]
    output_image: str
    watch_paths: list[str] = field(default_factory=list)

    @property
    def component_dir(self) -> str:
        return str(PurePosixPath(self.dockerfile).parent)

    @property
    def flavor(self) -> str:
        suffix = PurePosixPath(self.dockerfile).suffix  # .cuda
        return suffix.lstrip(".") or "cpu"

    def local_image_tag(self, suffix: str = "local") -> str:
        base = self.output_image.split(":", 1)[0]
        return f"{base}:{suffix}"


def _param_map(doc: dict) -> dict[str, object]:
    params: dict[str, object] = {}
    for entry in doc.get("spec", {}).get("params", []):
        params[entry["name"]] = entry.get("value")
    return params


NEGATED_PATH_CHANGED_RE = re.compile(
    r'!\s*(?:\(\s*)?"(?P<path>[^"]+)"\.pathChanged\(\)(?:\s*\))?'
)


def _extract_watch_paths(cel: str | None, tekton_path: Path) -> list[str]:
    paths: list[str] = []
    if cel:
        # Konflux CEL often negates paths (e.g. !("manifests/...".pathChanged())).
        # Only positive pathChanged() clauses should trigger a build.
        cleaned = NEGATED_PATH_CHANGED_RE.sub("", cel)
        paths.extend(PATH_CHANGED_RE.findall(cleaned))
    rel = tekton_path.relative_to(REPO_ROOT).as_posix()
    if rel not in paths:
        paths.append(rel)
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in paths:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def load_pipeline(path: Path) -> PipelineRun:
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    params = _param_map(doc)
    metadata = doc.get("metadata", {})
    annotations = metadata.get("annotations", {})
    labels = metadata.get("labels", {})
    cel = annotations.get("pipelinesascode.tekton.dev/on-cel-expression")

    build_args = params.get("build-args") or []
    if isinstance(build_args, str):
        build_args = [build_args]

    prefetch = params.get("prefetch-input") or []
    if isinstance(prefetch, str):
        prefetch = []

    platforms = params.get("build-platforms") or ["linux/amd64"]
    if isinstance(platforms, str):
        platforms = [platforms]

    return PipelineRun(
        path=path,
        name=metadata.get("name", path.stem),
        component=labels.get("appstudio.openshift.io/component", path.stem),
        dockerfile=str(params.get("dockerfile", "")),
        path_context=str(params.get("path-context", ".")),
        build_args_file=str(params.get("build-args-file") or ""),
        build_args=list(build_args),
        hermetic=str(params.get("hermetic", "false")).lower() == "true",
        prefetch_input=list(prefetch),
        build_platforms=list(platforms),
        output_image=str(params.get("output-image", "")),
        watch_paths=_extract_watch_paths(cel, path),
    )


def discover_pipelines(tekton_dir: Path = TEKTON_DIR) -> list[PipelineRun]:
    paths = sorted(tekton_dir.glob("*-pull-request.yaml"))
    return [load_pipeline(path) for path in paths]


def normalize_platform(platform: str) -> str:
    """Map Konflux MPC platforms to podman platform strings."""
    if platform.startswith("linux/"):
        arch = platform.split("/", 1)[1]
        if arch == "x86_64":
            return "linux/amd64"
        return platform
    if "/" in platform:
        arch = platform.rsplit("/", 1)[-1]
        if arch == "x86_64":
            arch = "amd64"
        return f"linux/{arch}"
    return platform


def platform_rpm_arch(platform: str) -> str:
    arch = normalize_platform(platform).split("/", 1)[-1]
    return PLATFORM_ARCH.get(arch, arch)


def platform_arch(platform: str) -> str:
    return normalize_platform(platform).split("/", 1)[-1]


def dedupe_platforms(platforms: list[str]) -> list[str]:
    """Normalize Konflux MPC labels and drop duplicate podman platforms."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in platforms:
        norm = normalize_platform(raw)
        if norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


def runner_for_platform(platform: str) -> str:
    norm = normalize_platform(platform)
    runner = PLATFORM_RUNNERS.get(norm)
    if not runner:
        raise SystemExit(f"No GHA runner mapping for platform {norm!r}")
    return runner


def needs_qemu(platform: str) -> bool:
    return normalize_platform(platform) in QEMU_PLATFORMS


def platform_slug(platform: str) -> str:
    return normalize_platform(platform).replace("/", "-")


def normalize_index_url(url: str) -> str:
    return url.rstrip("/")


def is_pypi_index_url(url: str) -> bool:
    return normalize_index_url(url) == normalize_index_url(PYPI_SIMPLE_INDEX)


def pip_index_url_from_requirements(requirements_path: Path) -> str | None:
    """Read --index-url from a requirements lockfile (RHOAI or PyPI)."""
    if not requirements_path.is_file():
        return None
    for raw in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("--index-url"):
            continue
        if "=" in line and not line.startswith("--index-url "):
            return line.split("=", 1)[1].strip()
        parts = line.split(None, 1)
        if len(parts) == 2:
            return parts[1].strip()
    return None


def validate_pip_requirements_index(platform: str | None, req_path: Path) -> None:
    """Ensure Hermeto will read a pip index from the lockfile (Konflux contract)."""
    rel = req_path.relative_to(REPO_ROOT)
    index_url = pip_index_url_from_requirements(req_path)
    if not index_url:
        print(
            f"WARN: {rel} has no --index-url; Hermeto defaults to PyPI.",
            flush=True,
        )
        return
    print(f"  pip index ({rel}): {index_url}", flush=True)
    if platform and not is_pypi_index_url(index_url):
        return
    arch = platform_arch(platform) if platform else None
    if arch in {"ppc64le", "s390x"} and is_pypi_index_url(index_url):
        print(
            f"WARN: {rel} uses PyPI on {arch}; many wheels are unavailable.",
            flush=True,
        )


def path_matches_watch(file_path: str, pattern: str) -> bool:
    file_path = file_path.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    if "**" in pattern:
        return PurePosixPath(file_path).match(pattern)
    return fnmatch.fnmatchcase(file_path, pattern)


def git_changed_files(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def pipeline_triggered(pipeline: PipelineRun, changed_files: list[str]) -> bool:
    if not changed_files:
        return False
    for changed in changed_files:
        for pattern in pipeline.watch_paths:
            if path_matches_watch(changed, pattern):
                return True
    return False


def prefetch_input_for_platform(
    prefetch_input: list[dict], platform: str | None = None
) -> list[dict]:
    """Return prefetch-input for Hermeto, matching Konflux MPC per-platform builds."""
    binary_arch = None
    if platform:
        binary_arch = PREFETCH_BINARY_ARCH.get(
            normalize_platform(platform).split("/", 1)[-1]
        )

    adjusted: list[dict] = []
    for entry in prefetch_input:
        item = dict(entry)
        if item.get("type") == "pip":
            binary = dict(DEFAULT_PIP_BINARY)
            binary.update(dict(item.get("binary") or {}))
            if binary_arch:
                binary["arch"] = binary_arch
            item["binary"] = binary
            for req in item.get("requirements_files") or []:
                req_path = REPO_ROOT / str(item.get("path") or ".") / str(req)
                validate_pip_requirements_index(platform, req_path)
        adjusted.append(item)
    return adjusted


def prefetch_input_json(pipeline: PipelineRun, platform: str | None = None) -> str:
    return json.dumps(
        prefetch_input_for_platform(pipeline.prefetch_input, platform),
        separators=(",", ":"),
    )


def run_prefetch(pipeline: PipelineRun, platform: str | None = None) -> None:
    if not pipeline.hermetic or not pipeline.prefetch_input:
        print("Skipping prefetch (not hermetic or no prefetch-input).", flush=True)
        return
    if not PREFETCH_SCRIPT.is_file():
        raise SystemExit(f"Missing prefetch script: {PREFETCH_SCRIPT}")

    env = os.environ.copy()
    env["INPUT_JSON"] = prefetch_input_json(pipeline, platform)
    env["SOURCE_DIR"] = str(REPO_ROOT)
    env["CONFIG_FILE"] = str(HERMETO_CONFIG.relative_to(REPO_ROOT))
    env.setdefault("LOG_LEVEL", "debug")
    env.setdefault("CONTAINER_ENGINE", os.environ.get("CONTAINER_ENGINE", "podman"))

    print("+", str(PREFETCH_SCRIPT), flush=True)
    print("  INPUT_JSON=", env["INPUT_JSON"], flush=True)
    subprocess.run([str(PREFETCH_SCRIPT)], cwd=REPO_ROOT, check=True, env=env)


def konflux_inline_build_args(pipeline: PipelineRun) -> list[str]:
    """Inline build-args for konflux-build-cli, mirroring Konflux PipelineRun params."""
    args = list(pipeline.build_args)
    if not any(arg.startswith("PYLOCK_FLAVOR=") for arg in args):
        args.insert(0, f"PYLOCK_FLAVOR={pipeline.flavor}")
    return args


def git_image_source() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "unknown"


def git_image_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "unknown"


def run_build_image(
    pipeline: PipelineRun, platform: str, tag: str | None = None
) -> None:
    """Build via build-konflux.sh (Konflux CLI on native arch, podman --platform on QEMU)."""
    if not BUILD_SCRIPT.is_file():
        raise SystemExit(f"Missing build script: {BUILD_SCRIPT}")

    platform = normalize_platform(platform)
    image_tag = tag or pipeline.local_image_tag()
    env = os.environ.copy()
    env["SOURCE_DIR"] = str(REPO_ROOT)
    env["IMAGE_TAG"] = image_tag
    env["DOCKERFILE"] = pipeline.dockerfile
    env["CONTEXT"] = pipeline.path_context
    env["BUILD_ARGS_FILE"] = pipeline.build_args_file
    env["BUILD_ARGS"] = " ".join(konflux_inline_build_args(pipeline))
    env["BUILD_PLATFORM"] = platform
    env["HERMETIC"] = "true" if pipeline.hermetic else "false"
    rpm_repos = REPO_ROOT / "cachi2/output/deps/rpm" / platform_rpm_arch(platform) / "repos.d"
    if rpm_repos.is_dir():
        env["YUM_REPOS_D_SOURCES"] = f"/cachi2/output/deps/rpm/{platform_rpm_arch(platform)}/repos.d"
    env.setdefault("CONTAINER_ENGINE", os.environ.get("CONTAINER_ENGINE", "podman"))
    env.setdefault("IMAGE_SOURCE", git_image_source())
    env.setdefault("IMAGE_REVISION", git_image_revision())

    print("+", str(BUILD_SCRIPT), flush=True)
    print("  PLATFORM=", platform, flush=True)
    print("  IMAGE_TAG=", image_tag, flush=True)
    print("  BUILD_ARGS=", env["BUILD_ARGS"], flush=True)
    subprocess.run([str(BUILD_SCRIPT)], cwd=REPO_ROOT, check=True, env=env)


def run_build(pipeline: PipelineRun, platform: str, tag: str | None = None) -> None:
    platform = normalize_platform(platform)
    if pipeline.hermetic and pipeline.prefetch_input:
        if not (REPO_ROOT / "cachi2/output").is_dir():
            raise SystemExit(
                "Hermetic build requires cachi2/output. Run: "
                f"make -f Makefile.tekton prefetch PIPELINE={pipeline.path.relative_to(REPO_ROOT)}"
            )
    run_build_image(pipeline, platform=platform, tag=tag)


def cmd_list(_: argparse.Namespace) -> None:
    for pipeline in discover_pipelines():
        print(
            f"{pipeline.path.name}\t{pipeline.component}\t{pipeline.dockerfile}\t"
            f"{','.join(normalize_platform(p) for p in pipeline.build_platforms)}"
        )


def cmd_show(args: argparse.Namespace) -> None:
    pipeline = load_pipeline((REPO_ROOT / args.pipeline).resolve())
    print(json.dumps(asdict(pipeline), indent=2, default=str))


def cmd_changed(args: argparse.Namespace) -> None:
    changed = git_changed_files(args.base, args.head)
    triggered = [
        pipeline
        for pipeline in discover_pipelines()
        if pipeline_triggered(pipeline, changed)
    ]
    if args.format == "json":
        payload = {
            "changed_files": changed,
            "pipelines": [
                {**asdict(pipeline), "path": pipeline.path.relative_to(REPO_ROOT).as_posix()}
                for pipeline in triggered
            ],
        }
        print(json.dumps(payload, indent=2))
        return

    for pipeline in triggered:
        print(pipeline.path.relative_to(REPO_ROOT))


def cmd_prefetch(args: argparse.Namespace) -> None:
    pipeline = load_pipeline((REPO_ROOT / args.pipeline).resolve())
    platform = args.platform or (
        normalize_platform(pipeline.build_platforms[0])
        if pipeline.build_platforms
        else None
    )
    run_prefetch(pipeline, platform=platform)


def cmd_build(args: argparse.Namespace) -> None:
    pipeline = load_pipeline((REPO_ROOT / args.pipeline).resolve())
    platform = args.platform or normalize_platform(pipeline.build_platforms[0])
    run_build(pipeline, platform=platform, tag=args.tag)


def matrix_platforms_for_pipeline(
    pipeline: PipelineRun, platform_override: str | None = None
) -> list[str]:
    if platform_override:
        return [normalize_platform(platform_override)]
    return dedupe_platforms(pipeline.build_platforms)


def gha_matrix_platforms(
    pipeline: PipelineRun, platform_override: str | None = None
) -> list[str]:
    """Platforms for GHA matrix jobs (subset of Konflux build-platforms).

    Konflux .tekton lists CUDA on ppc64le/s390x, but RHOAI cuda lockfiles only
    publish amd64/arm64 wheels — Hermeto correctly rejects missing arches.
    GHA skips CUDA on ppc/s390 for the same reason.
    """
    platforms = matrix_platforms_for_pipeline(pipeline, platform_override)
    excluded = GHA_EXCLUDED_PLATFORMS_BY_FLAVOR.get(pipeline.flavor, frozenset())
    if not excluded:
        return platforms
    kept: list[str] = []
    for platform in platforms:
        if platform in excluded:
            print(
                f"GHA matrix: skip {pipeline.component} on {platform} "
                f"({pipeline.flavor} has no RHOAI wheels for this arch)",
                file=sys.stderr,
                flush=True,
            )
            continue
        kept.append(platform)
    return kept


def cmd_matrix(args: argparse.Namespace) -> None:
    changed = git_changed_files(args.base, args.head)
    triggered = [
        pipeline
        for pipeline in discover_pipelines()
        if pipeline_triggered(pipeline, changed)
    ]
    include = []
    for pipeline in triggered:
        for platform in gha_matrix_platforms(pipeline, args.platform):
            include.append(
                {
                    "pipeline": pipeline.path.relative_to(REPO_ROOT).as_posix(),
                    "component": pipeline.component,
                    "platform": platform,
                    "platform_slug": platform_slug(platform),
                    "runner": runner_for_platform(platform),
                    "qemu": needs_qemu(platform),
                }
            )
    print(json.dumps({"include": include}, separators=(",", ":")))


def cmd_build_changed(args: argparse.Namespace) -> None:
    changed = git_changed_files(args.base, args.head)
    pipelines = [
        pipeline
        for pipeline in discover_pipelines()
        if pipeline_triggered(pipeline, changed)
    ]
    if not pipelines:
        print("No pipelines triggered by changes.", file=sys.stderr)
        return

    for pipeline in pipelines:
        for platform in matrix_platforms_for_pipeline(pipeline, args.platform):
            if args.prefetch:
                run_prefetch(pipeline, platform=platform)
            run_build(pipeline, platform=platform, tag=args.tag)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List Tekton PR pipelines").set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="Show parsed pipeline as JSON")
    show.add_argument("pipeline", help="Path to .tekton/*-pull-request.yaml")
    show.set_defaults(func=cmd_show)

    changed = sub.add_parser("changed", help="List pipelines triggered by git changes")
    changed.add_argument("--base", default="origin/main")
    changed.add_argument("--head", default="HEAD")
    changed.add_argument("--format", choices=["paths", "json"], default="paths")
    changed.set_defaults(func=cmd_changed)

    prefetch = sub.add_parser(
        "prefetch",
        help="Prefetch hermetic deps via Konflux hermeto image (prefetch-input from .tekton)",
    )
    prefetch.add_argument("pipeline", help="Path to .tekton/*-pull-request.yaml")
    prefetch.add_argument(
        "--platform",
        help="Target platform for pip binary arch (default: first build-platforms entry)",
    )
    prefetch.set_defaults(func=cmd_prefetch)

    build = sub.add_parser("build", help="Build one pipeline image")
    build.add_argument("pipeline", help="Path to .tekton/*-pull-request.yaml")
    build.add_argument("--platform", help="podman --platform (default: first build-platforms entry)")
    build.add_argument("--tag", help="Image tag override")
    build.set_defaults(func=cmd_build)

    matrix = sub.add_parser(
        "matrix",
        help="Emit GHA matrix JSON for pipelines triggered by git changes",
    )
    matrix.add_argument("--base", default="origin/main")
    matrix.add_argument("--head", default="HEAD")
    matrix.add_argument("--platform", help="Override platform for all matrix jobs")
    matrix.set_defaults(func=cmd_matrix)

    build_changed = sub.add_parser(
        "build-changed",
        help="Prefetch (optional) and build all pipelines triggered by git changes",
    )
    build_changed.add_argument("--base", default="origin/main")
    build_changed.add_argument("--head", default="HEAD")
    build_changed.add_argument("--platform", help="podman --platform override")
    build_changed.add_argument("--tag", help="Image tag override")
    build_changed.add_argument(
        "--prefetch",
        action="store_true",
        help="Run Hermeto prefetch before each build",
    )
    build_changed.set_defaults(func=cmd_build_changed)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    os.chdir(REPO_ROOT)
    args.func(args)


if __name__ == "__main__":
    main()
