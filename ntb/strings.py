"""String-manipulation utility functions for the notebook project."""

from __future__ import annotations

import textwrap
from string import templatelib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from os import PathLike

    import pytest_subtests
    from pyfakefs.fake_filesystem import FakeFilesystem


def indent(template: templatelib.Template) -> str:
    """Template-rendering function to render a t-string while preserving indentation,
    processing all the accustomed f-string formatters.
    References: https://www.pythonmorsels.com/t-strings-in-python/
    https://github.com/t-strings/pep750-examples/blob/main/pep/fstring.py"""
    parts = []
    indent = 0
    for item in template:
        match item:
            case templatelib.Interpolation(value, _expression, conversion, format_spec):
                value = templatelib.convert(value, conversion)
                value = format(value, format_spec)
                for i, line in enumerate(value.splitlines(keepends=True)):
                    parts.append(line if i == 0 else " " * indent + line)
            case str() as item:
                parts.extend(item.splitlines(keepends=True))
                indent = len(parts[-1]) - len(parts[-1].lstrip())
            case _:
                raise ValueError(f"Cannot happen: Unsupported item type: {type(item)}")
    return "".join(parts)


class TestProcessTemplateWithIndents:
    def test_process_template_with_indents(self, subtests: pytest_subtests.plugin.SubTests) -> None:
        a = "a\na"
        b = "b\n b"
        test_cases = [
            (t"", "", "empty string"),
            (t"a", "a", "single line"),
            (t"{a}", a, "single multiline substitution"),
            (t" {a}", textwrap.indent(a, prefix=" "), "substitution with leading whitespace"),
            (t" {b}", textwrap.indent(b, prefix=" "), "substitution whitespace before as well as inside"),
        ]
        for inp, expected, description in test_cases:
            with subtests.test(description):
                assert process_template_with_indents(inp) == expected


def blockinfile(
        filename: str | PathLike,
        contents: str,
        prefix: str | None = None,
        *,
        comment: str = "#",
) -> None:
    """This is similar to the functions in
    * https://homely.readthedocs.io/en/latest/ref/files.html#homely-files-blockinfile-1
    * ansible.modules.lineinfile
    """
    begin_marker = f"{comment * 3} BEGIN{' ' + prefix if prefix else ''}"
    end_marker = f"{comment * 3} END{' ' + prefix if prefix else ''}"

    begin = end = -1
    try:
        with open(filename, "rt") as fp:
            original_lines = fp.readlines()
    except OSError as e:
        raise RuntimeError(f"Failed to read {filename}: {e}") from e
    for line_no, line in enumerate(original_lines):
        if line.rstrip() == begin_marker:
            begin = line_no
        elif line.rstrip() == end_marker:
            end = line_no

    if begin != -1 and end == -1:
        raise ValueError(f"Found begin marker but no matching end marker in {filename}")
    if begin == -1 and end != -1:
        raise ValueError(f"Found end marker but no matching begin marker in {filename}")
    if begin > end:
        raise ValueError(f"Begin marker appears after end marker in {filename}")

    lines = original_lines[:]
    # NOTE: textwrap.dedent() with raw strings leaves leading and trailing newline
    #       we want to preserve the trailing one because HEREDOC has to have an empty trailing line for hadolint
    new_contents = contents.lstrip("\n").splitlines(keepends=True)
    if new_contents and new_contents[-1] == "\n":
        new_contents = new_contents[:-1]
    if begin == end == -1:
        # no markers found
        return
    else:
        lines[begin: end + 1] = [f"{begin_marker}\n", *new_contents, f"\n{end_marker}\n"]

    if lines == original_lines:
        return
    with open(filename, "wt") as fp:
        fp.writelines(lines)


class TestBlockinfile:
    def test_adding_new_block(self, fs: FakeFilesystem):
        """the file should not be modified if there is no block already"""
        fs.create_file("/config.txt", contents="hello\nworld")

        blockinfile("/config.txt", "key=value")

        assert fs.get_object("/config.txt").contents == "hello\nworld"

    def test_updating_value_in_block(self, fs: FakeFilesystem):
        fs.create_file("/config.txt", contents="hello\nworld\n### BEGIN\nkey=value1\n### END\n")

        blockinfile("/config.txt", "key=value2")

        assert fs.get_object("/config.txt").contents == "hello\nworld\n### BEGIN\nkey=value2\n### END\n"

    def test_lastnewline_removal(self, fs: FakeFilesystem):
        fs.create_file("/config.txt", contents="hello\nworld\n### BEGIN\n### END\n")

        blockinfile("/config.txt", "key=value\n\n")

        assert fs.get_object("/config.txt").contents == "hello\nworld\n### BEGIN\nkey=value\n\n### END\n"
