#!/usr/bin/env python3
"""Second-pass fixes for #3928 konflux Dockerfiles."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted(ROOT.glob("jupyter/**/Dockerfile.konflux.*"))

WHEEL_PREP = (
    "umask 0002\n"
    "python3 /usr/local/bin/prepare_group_writable_wheels.py /cachi2/output/deps/pip /tmp/pip-gw\n"
)

PERM_LINES = re.compile(
    r"\n(?:# Fix permissions[^\n]*\n)?"
    r"chmod -R g\+w /opt/app-root/lib/python3\.12/site-packages\n"
    r"fix-permissions /opt/app-root -P\n",
    re.MULTILINE,
)

TRUSTYAI_CHOWN = re.compile(
    r"\nRUN /bin/bash <<'EOF'\n"
    r"set -Eeuxo pipefail\n"
    r"# change ownership to default user \(all packages were installed as root and has root:root ownership\n"
    r"chown -R 1001:0 /opt/app-root/\n"
    r"chmod -R g=u /opt/app-root\n"
    r"EOF\n",
    re.MULTILINE,
)


def ensure_wheel_prep_in_uv_runs(text: str) -> str:
    parts = text.split("RUN /bin/bash <<'EOF'\n")
    out = [parts[0]]
    for block in parts[1:]:
        if "uv pip install" not in block:
            out.append("RUN /bin/bash <<'EOF'\n" + block)
            continue
        if "prepare_group_writable_wheels.py" not in block.split("EOF", 1)[0]:
            block = block.replace(
                "set -Eeuxo pipefail\n",
                f"set -Eeuxo pipefail\n{WHEEL_PREP}",
                1,
            )
        # umask without prepare (minimal case)
        elif "umask 0002\n" in block and "prepare_group_writable_wheels.py" not in block.split("EOF", 1)[0]:
            block = block.replace(
                "umask 0002\n\n",
                f"umask 0002\npython3 /usr/local/bin/prepare_group_writable_wheels.py /cachi2/output/deps/pip /tmp/pip-gw\n",
                1,
            )
        out.append("RUN /bin/bash <<'EOF'\n" + block)
    return "".join(out)


def patch_file(path: Path) -> None:
    text = path.read_text()
    text = text.replace("--find-links /cachi2/output/deps/pip \\", "--find-links /tmp/pip-gw \\")
    text = PERM_LINES.sub("\n", text)
    text = TRUSTYAI_CHOWN.sub("\n", text)
    text = ensure_wheel_prep_in_uv_runs(text)

    if "trustyai" in str(path):
        text = text.replace(
            "COPY ${TRUSTYAI_SOURCE_CODE}/requirements.${PYLOCK_FLAVOR}.txt ./requirements-trustyai.txt\n\nRUN /bin/bash",
            "COPY base-images/utils/prepare_group_writable_wheels.py /usr/local/bin/prepare_group_writable_wheels.py\n"
            "COPY ${TRUSTYAI_SOURCE_CODE}/requirements.${PYLOCK_FLAVOR}.txt ./requirements-trustyai.txt\n\n"
            "USER 1001:0\n\nRUN /bin/bash",
            1,
        )

    # Leaf GPU stages: install as 1001:0 when prepare script is present.
    text = re.sub(
        r"(COPY base-images/utils/prepare_group_writable_wheels\.py[^\n]+\n"
        r"(?:COPY \$\{[A-Z_]+\}/[^\n]+\n)+)\n\nUSER 0\n\nRUN /bin/bash",
        r"\1\n\nUSER 1001:0\n\nRUN /bin/bash",
        text,
        count=1,
    )
    text = re.sub(
        r"(COPY base-images/utils/prepare_group_writable_wheels\.py[^\n]+\n"
        r"(?:COPY \$\{[A-Z_]+\}/[^\n]+\n)+)\n\nUSER root\n\nRUN /bin/bash",
        r"\1\n\nUSER 1001:0\n\nRUN /bin/bash",
        text,
        count=1,
    )

    path.write_text(text)


def main() -> int:
    for path in FILES:
        patch_file(path)
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
