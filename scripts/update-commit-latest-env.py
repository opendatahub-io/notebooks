#!/usr/bin/env python3
"""Refresh ODH/RHOAI workbench ``commit-latest.env`` from ``vcs-ref`` image labels.

Both variants use ``manifests/odh/base/params-latest.env`` as the single source of
truth for which images exist — the RHOAI params-latest.env contains only dummy
placeholders and cannot be used for this purpose.

ODH variant:
  For each image, uses the tag declared in ``params-latest.env`` when that tag
  exists on quay.io/opendatahub (``vcs-ref`` label from the image config).
  When the declared tag is missing or unreachable, falls back to the most recently
  created ``main-<sha>`` tag as this is the builds from main tekton pipeline.
  Writes ``manifests/odh/base/commit-latest.env``.

RHOAI variant:
  Uses a ``rhoai-X.Y`` tag across all RHOAI images, extracting vcs-ref from each. Writes
  ``manifests/rhoai/base/commit-latest.env``.
  Tag selection priority:
    1) ``--rhoai-version-tag``
    2) ``GITHUB_REF_NAME`` when it matches ``rhoai-X.Y`` (for branch-driven GHA runs)
    3) auto-detected most recently created ``rhoai-X.Y`` tag on quay.io/rhoai
  Quay.io images are 1:1 mapped with the RedHat catalogue images, so vcs-ref remains the same.

Pipeline runtime images are intentionally skipped (only odh-workbench-* processed).

Usage (run from the repo root):

  # ODH only — quay.io/opendatahub, no auth required:
  uv run scripts/update-commit-latest-env.py --variant odh

  # RHOAI only — quay.io/rhoai, requires prior skopeo login:
  skopeo login quay.io --username <bot-user> --password <bot-token>
  uv run scripts/update-commit-latest-env.py --variant rhoai

  # Pin a specific RHOAI tag instead of auto-detecting:
  uv run scripts/update-commit-latest-env.py --variant rhoai --rhoai-version-tag rhoai-3.5

  # Both variants at once:
  uv run scripts/update-commit-latest-env.py --variant both
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import structlog

from ci.logging_config import configure_logging

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ODH_PARAMS_LATEST = PROJECT_ROOT / "manifests/odh/base/params-latest.env"
ODH_COMMIT_LATEST = PROJECT_ROOT / "manifests/odh/base/commit-latest.env"
RHOAI_COMMIT_LATEST = PROJECT_ROOT / "manifests/rhoai/base/commit-latest.env"

# Probe image used to discover the latest rhoai-X.Y tag
RHOAI_PROBE_IMAGE = "quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9"

QUAY_API_BASE = "https://quay.io/api/v1"
QUAY_PAGE_SIZE = 100
MAX_QUAY_PAGES = 50
SKOPEO_TIMEOUT_SEC = 60
SKOPEO_CONCURRENCY = 10

ODH_TAG_PATTERN = re.compile(r"^main-[0-9a-f]{40}$")
RHOAI_TAG_PATTERN = re.compile(r"^rhoai-\d+\.\d+$")

log = structlog.get_logger()


def load_workbench_images(params_path: pathlib.Path) -> list[tuple[str, str]]:
    """Return (variable, image_url) pairs for odh-workbench-* lines only."""
    result: list[tuple[str, str]] = []
    for line in params_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        variable, _, image_url = line.partition("=")
        if variable.startswith("odh-workbench-"):
            result.append((variable, image_url))
    return result


def _is_placeholder_image_url(image_url: str) -> bool:
    return not image_url or image_url.strip().lower() == "dummy"


def _is_rstudio_entry(variable: str, image_url: str) -> bool:
    token = f"{variable} {image_url}".lower()
    return "rstudio" in token


def _odh_image_base_from_variable(variable: str) -> str:
    image_name = variable.removesuffix("-n")
    return f"quay.io/opendatahub/{image_name}"


def rhoai_image_base(variable: str, odh_url: str) -> str:
    """Derive the quay.io/rhoai image base (no tag) from workbench metadata.

    quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:<tag>
    → quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9

    If the source URL is missing or a placeholder (e.g. ``dummy``), derive the
    ODH image base from the variable name to keep RHOAI updates working.
    """
    if _is_placeholder_image_url(odh_url) or not odh_url.startswith("quay.io/opendatahub/"):
        base = _odh_image_base_from_variable(variable)
        log.warning(
            "RHOAI: using ODH-derived image base fallback",
            variable=variable,
            source_image=odh_url,
            derived_base=base,
        )
    else:
        base = odh_url.rsplit(":", 1)[0]

    base = base.replace("quay.io/opendatahub/", "quay.io/rhoai/", 1)
    base = base.replace("-ubi9", "-rhel9")
    return base


def parse_image_ref(image_url: str) -> tuple[str, str]:
    """Return ``(repository_without_tag, tag)`` for a quay.io image reference."""
    if ":" not in image_url:
        return image_url, ""
    base, tag = image_url.rsplit(":", 1)
    return base, tag


def parse_quay_repository(image: str) -> tuple[str, str]:
    """Return (namespace, repository) for a quay.io image URL without tag."""
    candidate = image if "://" in image else f"https://{image}"
    parsed = urllib.parse.urlparse(candidate)
    if parsed.hostname != "quay.io":
        msg = f"not a quay.io repository: {image}"
        raise ValueError(msg)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        msg = f"invalid quay.io repository: {image}"
        raise ValueError(msg)
    namespace = parts[0]
    repository = "/".join(parts[1:])
    return namespace, repository


def normalize_rhoai_version_tag(value: str) -> str | None:
    """Return *value* when it is a ``rhoai-X.Y`` tag, otherwise ``None``."""
    return value if RHOAI_TAG_PATTERN.fullmatch(value) else None


def vcs_ref_from_odh_main_tag(tag: str) -> str | None:
    """Return the 7-char commit prefix encoded in a ``main-<sha>`` tag name."""
    if not ODH_TAG_PATTERN.match(tag):
        return None
    return tag.removeprefix("main-")[:7]


def vcs_ref_from_config(cfg: dict) -> str | None:
    labels = (cfg.get("config") or {}).get("Labels") or {}
    return labels.get("vcs-ref")


def commit_env_key(variable: str) -> str:
    return re.sub(r"-n$", "-commit-n", variable)


def write_commit_env(entries: list[tuple[str, str]], dest: pathlib.Path) -> None:
    with dest.open("wt", encoding="utf-8") as f:
        for key, value in sorted(entries):
            f.write(f"{key}={value}\n")
    log.info("wrote commit-latest.env", path=dest, entries=len(entries))


def _fetch_quay_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # ruff: ignore[suspicious-url-open-usage]
    try:
        with urllib.request.urlopen(request, timeout=SKOPEO_TIMEOUT_SEC) as response:  # ruff: ignore[suspicious-url-open-usage]
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError) as exc:
        msg = f"Quay API request failed for {url}: {exc}"
        raise ValueError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"Quay API returned invalid JSON for {url}"
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"Quay API returned invalid JSON object for {url}"
        raise ValueError(msg)
    return payload


async def quay_list_matching_tags(repository: str, pattern: re.Pattern) -> list[tuple[str, int]]:
    """Return ``(tag_name, start_ts)`` pairs for active tags matching *pattern*."""
    namespace, repo = parse_quay_repository(repository)
    tags: list[tuple[str, int]] = []
    page = 1

    while page <= MAX_QUAY_PAGES:
        url = (
            f"{QUAY_API_BASE}/repository/{namespace}/{repo}/tag/?limit={QUAY_PAGE_SIZE}&page={page}&onlyActiveTags=true"
        )
        try:
            payload = await asyncio.to_thread(_fetch_quay_json, url)
        except ValueError as exc:
            log.warning("quay list-tags unavailable, using skopeo fallback", repository=repository, error=str(exc))
            return []

        for tag in payload.get("tags", []):
            if not isinstance(tag, dict):
                continue
            name = tag.get("name")
            start_ts = tag.get("start_ts")
            if not isinstance(name, str) or not isinstance(start_ts, int):
                continue
            if pattern.match(name):
                tags.append((name, start_ts))

        if not payload.get("has_additional"):
            break
        page += 1
    else:
        log.warning("quay pagination exceeded max pages", repository=repository, max_pages=MAX_QUAY_PAGES)

    return tags


async def _communicate(proc: asyncio.subprocess.Process) -> tuple[bytes, bytes]:
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=SKOPEO_TIMEOUT_SEC)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise


async def skopeo_list_tags(image: str, semaphore: asyncio.Semaphore) -> list[str]:
    """Return all tags for the given image, or an empty list on failure."""
    cmd = ["skopeo", "list-tags", "--retry-times=3", f"docker://{image}"]
    try:
        async with semaphore:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await _communicate(proc)
    except FileNotFoundError:
        log.error("skopeo not found — please install it")
        return []
    except TimeoutError:
        log.error("list-tags timed out", image=image)
        return []

    if proc.returncode != 0:
        log.error("list-tags failed", image=image, stderr=stderr.decode().strip())
        return []

    try:
        payload = json.loads(stdout.decode())
    except json.JSONDecodeError:
        log.error("list-tags returned invalid JSON", image=image)
        return []

    tags = payload.get("Tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        log.error("list-tags returned invalid tags", image=image)
        return []
    return tags


async def skopeo_inspect_config(
    image_url: str,
    semaphore: asyncio.Semaphore,
    *,
    log_failure: bool = True,
) -> tuple[str, dict | None]:
    """Return (image_url, config) from skopeo inspect --config, or (image_url, None) on failure."""
    cmd = [
        "skopeo",
        "inspect",
        "--override-os=linux",
        "--override-arch=amd64",
        "--retry-times=3",
        "--config",
        f"docker://{image_url}",
    ]
    try:
        async with semaphore:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await _communicate(proc)
        if proc.returncode != 0:
            if log_failure:
                log.error("inspect failed", image=image_url, stderr=stderr.decode().strip())
            return image_url, None
        return image_url, json.loads(stdout.decode())
    except FileNotFoundError:
        if log_failure:
            log.error("skopeo not found — please install it")
        return image_url, None
    except TimeoutError:
        if log_failure:
            log.error("inspect timed out", image=image_url)
        return image_url, None
    except json.JSONDecodeError:
        if log_failure:
            log.error("failed to parse skopeo JSON", image=image_url)
        return image_url, None
    except Exception:
        if log_failure:
            log.exception("unexpected error", image=image_url)
        return image_url, None


async def find_latest_tag_by_skopeo_created(
    image: str,
    pattern: re.Pattern,
    semaphore: asyncio.Semaphore,
    *,
    log_failure: bool = True,
) -> str | None:
    """Return the most recently created tag on *image* matching *pattern*."""
    tags = await skopeo_list_tags(image, semaphore)
    matching = [tag for tag in tags if pattern.match(tag)]
    if not matching:
        log.error("no tags match pattern", image=image, pattern=pattern.pattern, sample=tags[:10])
        return None

    log.info("found candidate tags via skopeo", image=image, count=len(matching))
    inspected = await asyncio.gather(
        *[skopeo_inspect_config(f"{image}:{tag}", semaphore, log_failure=log_failure) for tag in matching]
    )

    best_tag: str | None = None
    best_created = ""
    for tag, (_, cfg) in zip(matching, inspected, strict=True):
        if cfg is None:
            continue
        created = cfg.get("created", "")
        if created > best_created:
            best_created = created
            best_tag = tag

    if best_tag is None:
        log.error("could not inspect any candidate tags", image=image)
        return None

    log.info("selected latest tag via skopeo", image=image, tag=best_tag, created=best_created)
    return best_tag


async def find_latest_odh_main_tag(image_base: str, semaphore: asyncio.Semaphore) -> str | None:
    """Return the most recently pushed ``main-<sha>`` tag for *image_base*."""
    matching = await quay_list_matching_tags(image_base, ODH_TAG_PATTERN)
    if matching:
        tag, start_ts = max(matching, key=lambda item: item[1])
        log.info("selected latest ODH main tag via Quay API", image=image_base, tag=tag, start_ts=start_ts)
        return tag

    log.info("discovering latest ODH main-<sha> tag via skopeo", image=image_base)
    # The fallback already logged why it is being used; keep per-tag inspect
    # failures quiet so a dead image does not flood the log.
    return await find_latest_tag_by_skopeo_created(image_base, ODH_TAG_PATTERN, semaphore, log_failure=False)


async def resolve_odh_vcs_ref(
    base: str,
    pinned_tag: str,
    semaphore: asyncio.Semaphore,
) -> str | None:
    """Resolve a 7-char commit prefix from a pinned tag or latest ``main-<sha>`` fallback."""
    if pinned_tag:
        image_url = f"{base}:{pinned_tag}"
        _, cfg = await skopeo_inspect_config(image_url, semaphore, log_failure=False)
        if cfg is not None:
            vcs_ref = vcs_ref_from_config(cfg)
            if vcs_ref:
                log.info("ODH: using pinned tag from params-latest.env", image=base, tag=pinned_tag)
                return vcs_ref[:7]
            log.warning(
                "ODH: vcs-ref label missing on pinned tag, falling back to latest main-<sha>",
                image=image_url,
            )
        else:
            log.warning(
                "ODH: pinned tag not found or not accessible, falling back to latest main-<sha>",
                image=base,
                tag=pinned_tag,
            )

    tag = await find_latest_odh_main_tag(base, semaphore)
    if tag is None:
        return None
    return vcs_ref_from_odh_main_tag(tag)


async def find_latest_rhoai_tag_by_created(image: str, semaphore: asyncio.Semaphore) -> str | None:
    """Return the most recently created ``rhoai-X.Y`` tag on *image*."""
    # log_failure=True (the default) matches the pre-merge RHOAI behavior.
    return await find_latest_tag_by_skopeo_created(image, RHOAI_TAG_PATTERN, semaphore, log_failure=True)


async def collect_odh_entries(
    workbench_images: list[tuple[str, str]],
    semaphore: asyncio.Semaphore,
) -> list[tuple[str, str]] | None:
    async def process_one(variable: str, odh_url: str) -> tuple[str, str] | None:
        base, pinned_tag = parse_image_ref(odh_url)
        vcs_ref = await resolve_odh_vcs_ref(base, pinned_tag, semaphore)
        if vcs_ref is None:
            return None
        return commit_env_key(variable), vcs_ref

    results = await asyncio.gather(*[process_one(variable, odh_url) for variable, odh_url in workbench_images])
    if any(result is None for result in results):
        return None
    return list(results)


async def resolve_rhoai_version_tag(
    args: argparse.Namespace,
    semaphore: asyncio.Semaphore,
) -> str | None:
    if args.rhoai_version_tag:
        normalized = normalize_rhoai_version_tag(args.rhoai_version_tag)
        if normalized:
            log.info("using RHOAI tag from --rhoai-version-tag", tag=normalized)
            return normalized
        log.error("invalid RHOAI version tag", tag=args.rhoai_version_tag)
        return None

    branch = os.environ.get("GITHUB_REF_NAME", "")
    normalized = normalize_rhoai_version_tag(branch)
    if normalized:
        log.info("using RHOAI tag from branch name", branch=branch, tag=normalized)
        return normalized

    log.info("auto-detecting latest RHOAI tag from quay.io/rhoai...")
    return await find_latest_rhoai_tag_by_created(RHOAI_PROBE_IMAGE, semaphore)


async def collect_rhoai_entries(
    workbench_images: list[tuple[str, str]],
    rhoai_tag: str,
    semaphore: asyncio.Semaphore,
) -> list[tuple[str, str]] | None:
    async def process_one(variable: str, odh_url: str) -> tuple[str, str] | None:
        if _is_rstudio_entry(variable, odh_url):
            log.info("RHOAI: skipping RStudio workbench entry", variable=variable)
            return "", ""

        image_url = f"{rhoai_image_base(variable, odh_url)}:{rhoai_tag}"
        _, cfg = await skopeo_inspect_config(image_url, semaphore)
        if cfg is None:
            log.error("RHOAI: inspect failed", image=image_url)
            return None
        vcs_ref = vcs_ref_from_config(cfg)
        if not vcs_ref:
            log.warning("RHOAI: vcs-ref label missing", image=image_url)
            return None
        return commit_env_key(variable), vcs_ref[:7]

    results = await asyncio.gather(*[process_one(variable, odh_url) for variable, odh_url in workbench_images])
    if any(result is None for result in results):
        return None
    entries = [entry for entry in results if entry and entry[0]]
    if not entries:
        log.error("RHOAI: no workbench entries produced after filtering")
        return None
    return entries


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variant",
        choices=["odh", "rhoai", "both"],
        default="odh",
        help=(
            "'odh' (default): update ODH commit-latest.env only; "
            "'rhoai': update RHOAI commit-latest.env only; "
            "'both': update both"
        ),
    )
    parser.add_argument(
        "--rhoai-version-tag",
        default=None,
        help=(
            "Pin a specific RHOAI tag (e.g. 'rhoai-3.5'). "
            "When omitted the script uses GITHUB_REF_NAME when it matches rhoai-X.Y; "
            "otherwise it auto-detects the most recently created rhoai-X.Y tag."
        ),
    )
    args = parser.parse_args()

    workbench_images = load_workbench_images(ODH_PARAMS_LATEST)
    if not workbench_images:
        log.error("no workbench images found in ODH params-latest.env")
        sys.exit(1)

    run_odh = args.variant in ("odh", "both")
    run_rhoai = args.variant in ("rhoai", "both")
    semaphore = asyncio.Semaphore(SKOPEO_CONCURRENCY)

    if run_odh:
        odh_entries = await collect_odh_entries(workbench_images, semaphore)
        if odh_entries is None:
            log.error("ODH: one or more images could not be processed")
            sys.exit(1)
        write_commit_env(odh_entries, ODH_COMMIT_LATEST)

    if run_rhoai:
        rhoai_tag = await resolve_rhoai_version_tag(args, semaphore)
        if not rhoai_tag:
            log.error(
                "cannot determine RHOAI version tag — "
                "pass --rhoai-version-tag, run on a rhoai-X.Y branch, "
                "or ensure skopeo is logged into quay.io for auto-detection"
            )
            sys.exit(1)

        log.info("using RHOAI tag", tag=rhoai_tag)
        rhoai_entries = await collect_rhoai_entries(workbench_images, rhoai_tag, semaphore)
        if rhoai_entries is None:
            log.error("RHOAI: one or more images could not be processed")
            sys.exit(1)
        write_commit_env(rhoai_entries, RHOAI_COMMIT_LATEST)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
