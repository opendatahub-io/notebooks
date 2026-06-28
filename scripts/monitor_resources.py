#! /usr/bin/env python3

import time
import subprocess
import os
import shutil
import structlog
from ci.logging_config import configure_logging

configure_logging()
log = structlog.get_logger()

def get_disk_usage(path: str) -> str:
    if not os.path.exists(path):
        return "not found"

    result = subprocess.run(['df', '-h', path], capture_output=True, text=True)
    if result.returncode != 0:
        return "error"

    # The output format is generally:
    # Filesystem      Size  Used Avail Use% Mounted on
    # ...
    lines = result.stdout.splitlines()
    if len(lines) > 1:
        return lines[1].split()[4]
    return "unknown format"

def get_memory_usage() -> str:
    if not shutil.which('free'):
        return "free command not found"
    result = subprocess.run(['free', '-h'], capture_output=True, text=True)
    if result.returncode == 0:
        # Just grab the 'Mem:' line and maybe 'Swap:'?
        # The bash command outputted everything from free -h
        return result.stdout.strip()
    return "error"

def main() -> None:
    # Common system container paths and partitions
    paths_to_monitor: list[str] = ['/', '/mnt', '/var/lib/containers']
    
    log.info("Starting resource monitoring")
    
    while True:
        log.info("Resource stats", 
                 disk={path: get_disk_usage(path) for path in paths_to_monitor},
                 memory=get_memory_usage())
        time.sleep(30)

if __name__ == "__main__":
    main()
