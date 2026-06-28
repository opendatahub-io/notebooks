#! /usr/bin/env python3

import shutil
import subprocess
import time

import structlog

from ci.logging_config import configure_logging

configure_logging()
log = structlog.get_logger()

_HAS_FREE = shutil.which("free") is not None

PATHS_TO_MONITOR: list[str] = ["/", "/mnt", "/mnt/containers/storage"]


def get_disk_usage(path: str) -> dict[str, str]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {"status": "not found"}
    pct = usage.used / usage.total * 100 if usage.total else 0
    gib_free = usage.free / (1024**3)
    return {"used_pct": f"{pct:.0f}%", "free_gib": f"{gib_free:.1f}"}


def get_memory_usage() -> dict[str, str]:
    if not _HAS_FREE:
        return {}
    result = subprocess.run(["free", "-h"], capture_output=True, text=True)
    if result.returncode != 0:
        return {"status": "error"}
    info: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts and parts[0] == "Mem:":
            info["mem_total"] = parts[1]
            info["mem_used"] = parts[2]
            info["mem_free"] = parts[3]
        elif parts and parts[0] == "Swap:":
            info["swap_total"] = parts[1]
            info["swap_used"] = parts[2]
    return info


def main() -> None:
    log.info("Starting resource monitoring")

    while True:
        log.info(
            "Resource stats",
            disk={path: get_disk_usage(path) for path in PATHS_TO_MONITOR},
            memory=get_memory_usage(),
        )
        time.sleep(30)


if __name__ == "__main__":
    main()
