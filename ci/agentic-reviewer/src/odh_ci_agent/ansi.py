"""ANSI escape sequence helpers shared by CI tooling."""

from __future__ import annotations

import re

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9:;<=>?]*[ -/]*[@-~]|\x1b\].*?(?:\x07|\x1b\\)")
