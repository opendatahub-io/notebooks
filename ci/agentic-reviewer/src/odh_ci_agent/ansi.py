"""ANSI escape sequence helpers shared by CI tooling."""

from __future__ import annotations

import re

# Keep the OSC branch explicit and single-line; an unbounded ``.*?`` can
# repeatedly rescan unterminated attacker-controlled sequences quadratically.
ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9:;<=>?]*[ -/]*[@-~]"
    r"|\x1b\](?:[^\x07\x1b\r\n]|\x1b(?!\\))*(?:\x07|\x1b\\|$)"
)
