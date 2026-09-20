"""ANSI escape sequence helpers shared by CI tooling."""

from __future__ import annotations

import re

# Keep the OSC branch explicit and single-line; an unbounded ``.*?`` can
# repeatedly rescan unterminated attacker-controlled sequences quadratically.
ANSI_ESCAPE_RE = re.compile(
    r"""
    \x1b\[                    # CSI introducer
    [0-9:;<=>?]*             # parameter bytes
    [ -/]*                    # intermediate bytes
    [@-~]                     # final byte
    |
    \x1b\]                    # OSC introducer
    (?:[^\x07\x1b\r\n]|\x1b(?!\\))*  # payload, without BEL or ST
    (?:\x07|\x1b\\|$)        # BEL, ST, or end of line
    """,
    re.VERBOSE,
)
