"""Parse PR file patches into commentable diff line numbers for review tools."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_patch_commentable_lines(patch: str | None) -> tuple[set[int], set[int]]:
    """Return commentable 1-based line numbers on RIGHT (+) and LEFT (-) sides."""

    right_lines: set[int] = set()
    left_lines: set[int] = set()
    if not patch:
        return right_lines, left_lines

    right_line = 0
    left_line = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            match = _HUNK_RE.match(line)
            if match:
                left_line = int(match.group(1))
                right_line = int(match.group(3))
            continue
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("+") and not line.startswith("++"):
            right_lines.add(right_line)
            right_line += 1
            continue
        if line.startswith("-") and not line.startswith("--"):
            left_lines.add(left_line)
            left_line += 1
            continue
        if line.startswith(" "):
            right_line += 1
            left_line += 1
            continue
        if line.startswith("\\"):
            continue

    return right_lines, left_lines


def format_line_range(lines: set[int]) -> str:
    if not lines:
        return "(none)"
    ordered = sorted(lines)
    if len(ordered) <= 12:
        return ", ".join(str(number) for number in ordered)
    return f"{ordered[0]}-{ordered[-1]} ({len(ordered)} changed lines)"


@dataclass
class DiffLineIndex:
    """Commentable line numbers per changed file path and diff side."""

    right: dict[str, set[int]] = field(default_factory=dict)
    left: dict[str, set[int]] = field(default_factory=dict)

    @classmethod
    def from_pull_files(cls, files: Sequence[object]) -> DiffLineIndex:
        index = cls()
        for file_info in files:
            if not isinstance(file_info, Mapping):
                continue
            filename = file_info.get("filename")
            if not isinstance(filename, str):
                continue
            patch = file_info.get("patch")
            right_lines, left_lines = parse_patch_commentable_lines(patch if isinstance(patch, str) else None)
            index.right[filename] = right_lines
            index.left[filename] = left_lines
        return index

    def known_paths(self) -> set[str]:
        return set(self.right) | set(self.left)

    def validate_comment(
        self,
        *,
        path: str,
        line: int,
        side: str,
        start_line: int | None = None,
    ) -> str | None:
        normalized_side = side.upper()
        if normalized_side not in {"LEFT", "RIGHT"}:
            return f"Invalid side {side!r}; use LEFT or RIGHT"

        if path not in self.known_paths():
            return f"Path {path!r} is not part of the pull request diff"

        commentable = self.right[path] if normalized_side == "RIGHT" else self.left[path]
        if not commentable:
            return (
                f"Path {path!r} has no commentable changed lines on {normalized_side} side "
                "(patch unavailable, binary file, or no +/- lines on that side)"
            )

        if line not in commentable:
            return (
                f"Line {line} could not be resolved for {path} on {normalized_side} side; "
                f"commentable {normalized_side} lines: {format_line_range(commentable)}"
            )

        if start_line is not None:
            if start_line not in commentable:
                return (
                    f"startLine {start_line} could not be resolved for {path} on {normalized_side} side; "
                    f"commentable {normalized_side} lines: {format_line_range(commentable)}"
                )
            if start_line > line:
                return f"startLine {start_line} must be <= line {line}"

        return None
