#!/usr/bin/env python3
from __future__ import annotations
"""
Reproduce kubelet httpGet probe logic for the supplied path.
Exits 0 if the probe will eventually pass, 1 otherwise.
"""
import sys
import time
from http.client import HTTPConnection, HTTPSConnection
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Type

# probe constants from the odh-dashboard Deployment
# https://github.com/opendatahub-io/odh-dashboard/blob/2.4.0-release/backend/src/utils/notebookUtils.ts#L310-L332
INITIAL_DELAY = 10
PERIOD        = 5
TIMEOUT       = 1
FAIL_THRESH   = 3
SUCCESS_THRESH = 1

def probe_once(connection_factory: Type[HTTPConnection], host: str, port: int, path: str) -> tuple[bool, str]:
    conn = None
    try:
        conn = connection_factory(host, port, timeout=TIMEOUT)
        conn.request("GET", path)
        resp = conn.getresponse()
        return 200 <= resp.status < 400, resp.status
    except Exception as e:
        return False, str(e)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def main() -> int:
    if len(sys.argv) != 4:
        print("usage: probe_check.py <namespace> <name> <notebook-port>", file=sys.stderr)
        return 2

    namespace, name, port = sys.argv[1:]
    path = f"/notebook/{namespace}/{name}/api"

    # kubelet waits initialDelaySeconds before the first probe
    time.sleep(INITIAL_DELAY)

    consecutive_failures = 0
    consecutive_successes = 0

    while True:
        ok, err = probe_once(HTTPConnection, "127.0.0.1", int(port), path)
        print("probe_once:", ok, err)

        if ok:
            consecutive_successes += 1
            consecutive_failures = 0
            if consecutive_successes >= SUCCESS_THRESH:
                return 0
        else:
            consecutive_failures += 1
            consecutive_successes = 0
            if consecutive_failures >= FAIL_THRESH:
                return 1

        time.sleep(PERIOD)

if __name__ == "__main__":
    sys.exit(main())
