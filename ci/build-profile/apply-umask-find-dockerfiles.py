#!/usr/bin/env python3
"""Apply USER 1001:0 + umask 0002 + ensure-openshift-site-packages to konflux Dockerfiles."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted(ROOT.glob("jupyter/**/Dockerfile.konflux.*"))

ENSURE_COPY = (
    "COPY base-images/utils/ensure-openshift-site-packages.sh "
    "/usr/local/bin/ensure-openshift-site-packages.sh\n"
)

WHEEL_COPY = re.compile(
    r"COPY base-images/utils/prepare_group_writable_wheels\.py "
    r"/usr/local/bin/prepare_group_writable_wheels\.py\n"
)
WHEEL_PREP = re.compile(
    r"python3 /usr/local/bin/prepare_group_writable_wheels\.py "
    r"/cachi2/output/deps/pip /tmp/pip-gw\n"
)
PIP_GW = "--find-links /tmp/pip-gw \\"
PIP_CACHI = "--find-links /cachi2/output/deps/pip \\"


def patch_run_block(text: str) -> str:
    if "ensure-openshift-site-packages.sh" in text and WHEEL_COPY.search(text) is None:
        # Already patched; ensure ensure script is invoked before EOF
        if "/usr/local/bin/ensure-openshift-site-packages.sh" not in text:
            text = text.replace(
                "/opt/app-root/bin/utils/addons/apply.sh\nEOF",
                "/opt/app-root/bin/utils/addons/apply.sh\n"
                "/usr/local/bin/ensure-openshift-site-packages.sh\nEOF",
            )
        return text

    text = WHEEL_COPY.sub(ENSURE_COPY, text)
    text = WHEEL_PREP.sub("", text)
    text = text.replace(PIP_GW, PIP_CACHI)

    if "umask 0002" not in text:
        text = text.replace(
            "set -Eeuxo pipefail\n",
            "set -Eeuxo pipefail\numask 0002\n",
            1,
        )

    if "/usr/local/bin/ensure-openshift-site-packages.sh" not in text:
        text = text.replace(
            "/opt/app-root/bin/utils/addons/apply.sh\nEOF",
            "/opt/app-root/bin/utils/addons/apply.sh\n"
            "/usr/local/bin/ensure-openshift-site-packages.sh\nEOF",
        )
        # trustyai: uv block ends without apply in same heredoc
        text = text.replace(
            "--requirements=./requirements-trustyai.txt\nEOF",
            "--requirements=./requirements-trustyai.txt\n"
            "/usr/local/bin/ensure-openshift-site-packages.sh\nEOF",
        )

    return text


def patch_file(path: Path) -> bool:
    original = path.read_text()
    text = patch_run_block(original)
    if text == original:
        return False
    path.write_text(text)
    return True


def main() -> int:
    changed = 0
    for path in FILES:
        if patch_file(path):
            print(f"patched {path.relative_to(ROOT)}")
            changed += 1
    print(f"changed {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
