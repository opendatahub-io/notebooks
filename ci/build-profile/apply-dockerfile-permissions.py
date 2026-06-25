#!/usr/bin/env python3
"""Apply #3928 ownership model to konflux Jupyter Dockerfiles."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KONFLUX_DOCKERFILES = sorted(ROOT.glob("jupyter/**/Dockerfile.konflux.*"))

PREPARE_COPY = "COPY base-images/utils/prepare_group_writable_wheels.py /usr/local/bin/prepare_group_writable_wheels.py\n"

PERM_BLOCK = re.compile(
    r"\n# Fix permissions to support pip in Openshift environments\n"
    r"chmod -R g\+w /opt/app-root/lib/python3\.12/site-packages\n"
    r"fix-permissions /opt/app-root -P\n",
    re.MULTILINE,
)

ROOT_UV_COMMENT = re.compile(
    r"# hadolint ignore=DL3002\n"
    r"# Run as root \(same as jupyter-minimal\): uv from cpu-base is root-owned; chmod g\+w must be root\.\n",
    re.MULTILINE,
)

UV_RUN = re.compile(
    r"(RUN /bin/bash <<'EOF'\nset -Eeuxo pipefail\n)"
    r"(?:(?!EOF\n).)*?"
    r"(uv pip install[^\n]*\n(?:[^\n]*\n)*?--find-links )"
    r"/cachi2/output/deps/pip( \\)",
    re.MULTILINE | re.DOTALL,
)


def patch_uv_run(match: re.Match[str]) -> str:
    prefix = match.group(1)
    middle = match.group(2)
    suffix = match.group(3)
    if "prepare_group_writable_wheels.py" in middle:
        return match.group(0)
    insert = (
        "umask 0002\n"
        "python3 /usr/local/bin/prepare_group_writable_wheels.py /cachi2/output/deps/pip /tmp/pip-gw\n"
    )
    if 'echo "Installing software and packages"\n' in middle:
        middle = middle.replace(
            'echo "Installing software and packages"\n',
            f"{insert}echo \"Installing software and packages\"\n",
            1,
        )
    else:
        middle = insert + middle
    return f"{prefix}{middle}{suffix}/tmp/pip-gw{match.group(4)}"


def add_prepare_copy(text: str) -> str:
    if PREPARE_COPY.strip() in text:
        return text
    markers = [
        "COPY --chown=1001:0 ${MINIMAL_SOURCE_CODE}/uv.lock.d",
        "COPY ${DATASCIENCE_SOURCE_CODE}/requirements.",
        "COPY ${PYTORCH_SOURCE_CODE}/uv.lock.d",
        "COPY ${TENSORFLOW_SOURCE_CODE}/uv.lock.d",
        "COPY ${TRUSTYAI_SOURCE_CODE}/uv.lock.d",
        "COPY ${LLMCOMPRESSOR_SOURCE_CODE}/uv.lock.d",
    ]
    for marker in markers:
        if marker in text:
            return text.replace(marker, f"{PREPARE_COPY}{marker}", 1)
    return text


def set_user_before_uv_run(text: str) -> str:
    """Use 1001:0 for uv install RUN blocks that follow chown COPYs."""
    pattern = re.compile(
        r"(COPY --chown=1001:0[^\n]+\n(?:COPY --chown=1001:0[^\n]+\n)*)"
        r"\n(?:USER 0\n\n)?RUN /bin/bash <<'EOF'\nset -Eeuxo pipefail\n"
        r"(?:umask 0002\n)?(?:python3 /usr/local/bin/prepare_group_writable_wheels\.py[^\n]+\n)?",
        re.MULTILINE,
    )
    return pattern.sub(
        lambda m: f"{m.group(1)}\n\nUSER 1001:0\n\nRUN /bin/bash <<'EOF'\nset -Eeuxo pipefail\n"
        f"{'umask 0002\n' if 'umask 0002' in m.group(0) else 'umask 0002\n'}"
        f"{'python3 /usr/local/bin/prepare_group_writable_wheels.py /cachi2/output/deps/pip /tmp/pip-gw\n' if 'prepare_group_writable_wheels' in m.group(0) else ''}",
        text,
        count=1,
    )


def set_leaf_user(text: str) -> str:
    """Leaf stages that COPY uv.lock as root should switch to 1001:0 before RUN."""
    return re.sub(
        r"(COPY base-images/utils/prepare_group_writable_wheels\.py[^\n]+\n"
        r"COPY \$\{[A-Z_]+\}/uv\.lock\.d[^\n]+\n"
        r"COPY \$\{[A-Z_]+\}/requirements\.[^\n]+\n)\n\nRUN /bin/bash",
        r"\1\n\nUSER 1001:0\n\nRUN /bin/bash",
        text,
        count=1,
    )


def set_datascience_user(text: str) -> str:
    if "jupyter-datascience" not in text:
        return text
    return re.sub(
        r"(COPY \$\{DATASCIENCE_SOURCE_CODE\}/setup-elyra\.sh[^\n]+\n)\n(?:USER 0\n\n)?RUN /bin/bash",
        r"\1\nUSER 1001:0\n\nRUN /bin/bash",
        text,
        count=1,
    )


def patch_file(path: Path) -> bool:
    original = path.read_text()
    text = original
    text = PERM_BLOCK.sub("\n", text)
    text = ROOT_UV_COMMENT.sub("", text)
    text = UV_RUN.sub(patch_uv_run, text)
    text = add_prepare_copy(text)
    text = set_user_before_uv_run(text)
    text = set_leaf_user(text)
    text = set_datascience_user(text)

    if text == original:
        return False
    path.write_text(text)
    return True


def main() -> int:
    changed = 0
    for path in KONFLUX_DOCKERFILES:
        if patch_file(path):
            print(f"patched {path.relative_to(ROOT)}")
            changed += 1
    print(f"changed {changed} konflux dockerfiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
