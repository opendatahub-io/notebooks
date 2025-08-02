#!/usr/bin/env python3
from __future__ import annotations

import os
import textwrap
import pathlib

ROOT_DIR = pathlib.Path(__file__).parent.parent


def main():
    for dockerfile in ROOT_DIR.glob("**/Dockerfile*"):
        blockinfile(
            dockerfile,
            textwrap.dedent(
                r"""
                RUN curl -L https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz \
                        -o /tmp/openshift-client-linux.tar.gz && \
                    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
                    rm -f /tmp/openshift-client-linux.tar.gz
            """
            ),
            prefix="Install the oc client",
        )


def blockinfile(filename: str | os.PathLike, contents: str, prefix: str | None = None, *, comment: str = "#"):
    """This is similar to the functions in
    * https://homely.readthedocs.io/en/latest/ref/files.html#homely-files-blockinfile-1
    * ansible.modules.lineinfile
    """
    begin_marker = f"{comment} {prefix if prefix else ''} begin"
    end_marker = f"{comment} {prefix if prefix else ''} end"

    begin = end = -1
    try:
        with open(filename, "rt") as fp:
            original_lines = fp.readlines()
    except (IOError, OSError) as e:
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
    new_contents = contents.strip("\n").splitlines(keepends=True)
    if begin == end == -1:
        # add at the end if no markers found
        lines.append(f"\n{begin_marker}\n")
        lines.extend(new_contents)
        lines.append(f"\n{end_marker}\n")
    else:
        lines[begin : end + 1] = [f"{begin_marker}\n", *new_contents, f"\n{end_marker}\n"]

    if lines == original_lines:
        return
    with open(filename, "wt") as fp:
        fp.writelines(lines)


if __name__ == "__main__":
    main()


class TestBlockinfile:
    from pyfakefs.fake_filesystem import FakeFilesystem

    def test_adding_new_block(self, fs: FakeFilesystem):
        fs.create_file("/config.txt", contents="hello\nworld")

        blockinfile("/config.txt", "key=value")

        assert fs.get_object("/config.txt").contents == "hello\nworld\n#  begin\nkey=value\n#  end\n"

    def test_updating_value_in_block(self, fs: FakeFilesystem):
        fs.create_file("/config.txt", contents="hello\nworld\n#  begin\nkey=value1\n#  end\n")

        blockinfile("/config.txt", "key=value2")

        assert fs.get_object("/config.txt").contents == "hello\nworld\n#  begin\nkey=value2\n#  end\n"
