#!/usr/bin/env python3
from __future__ import annotations

"""
This script is inspired by the AIPCC `replace-markers.sh` script, invoked from `make regen`
  https://gitlab.com/redhat/rhel-ai/core/base-images/app/-/blob/main/containerfiles/replace-markers.sh

The original AIPCC version uses the `ed` command to replace everything between
 `### BEGIN <filename>` and `### END <filename>` with the content of the <filename>.

This script currently has the data inline, but this can be easily changed.
We could also support files, or maybe even `### BEGIN funcname("param1", "param2")` that would
 run Python function `funcname` and paste in the return value.
"""

import os
import textwrap
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyfakefs.fake_filesystem import FakeFilesystem

ROOT_DIR = pathlib.Path(__file__).parent.parent


def main():
    for dockerfile in ROOT_DIR.glob("**/Dockerfile*"):
        if not dockerfile.is_file():
            continue
        if dockerfile.is_relative_to(ROOT_DIR / "base-images"):
            continue
        if dockerfile.is_relative_to(ROOT_DIR / "examples"):
            continue

        replacements = {
            "upgrade first to avoid fixable vulnerabilities": textwrap.dedent(r"""
                # If we have a Red Hat subscription prepared, refresh it
                RUN /bin/bash <<'EOF'
                set -Eeuxo pipefail
                if command -v subscription-manager &> /dev/null; then
                  subscription-manager identity &>/dev/null && subscription-manager refresh || echo "No identity, skipping refresh."
                fi
                EOF

                # Problem: The operation would result in removing the following protected packages: systemd
                #  (try to add '--allowerasing' to command line to replace conflicting packages or '--skip-broken' to skip uninstallable packages)
                # Solution: --best --skip-broken does not work either, so use --nobest
                RUN --mount=type=cache,target=/var/cache/dnf,sharing=locked,id=notebooks-dnf /bin/bash <<'EOF'
                set -Eeuxo pipefail
                dnf -y upgrade --refresh --nobest --skip-broken --nodocs --noplugins --setopt=install_weak_deps=0 --setopt=keepcache=1
                EOF

            """),
            "Install micropipenv and uv to deploy packages from requirements.txt": '''RUN pip install --no-cache-dir --extra-index-url https://pypi.org/simple -U "micropipenv[toml]==1.9.0" "uv==0.9.6"''',
            "Install the oc client": textwrap.dedent(r"""
                RUN /bin/bash <<'EOF'
                set -Eeuxo pipefail
                curl -L https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz \
                    -o /tmp/openshift-client-linux.tar.gz
                tar -xzvf /tmp/openshift-client-linux.tar.gz oc
                rm -f /tmp/openshift-client-linux.tar.gz
                EOF

            """),
            "Dependencies for PDF export": textwrap.dedent(r"""
                RUN ./utils/install_pdf_deps.sh
                ENV PATH="/usr/local/texlive/bin/linux:/usr/local/pandoc/bin:$PATH"
            """),
            "Download Elyra Bootstrapper": textwrap.dedent(r"""
                RUN curl -fL https://raw.githubusercontent.com/opendatahub-io/elyra/refs/tags/v4.3.1/elyra/kfp/bootstrapper.py \
                         -o ./utils/bootstrapper.py
                # Prevent Elyra from re-installing the dependencies
                ENV ELYRA_INSTALL_PACKAGES="false"
            """),
        }

        # sanity check that we don't have any unexpected `### BEGIN`s and `### END`s
        begin = "#" * 3 + " BEGIN"
        end = "#" * 3 + " END"
        with open(dockerfile, "rt") as fp:
            for line_no, line in enumerate(fp, start=1):
                for prefix in (begin, end):
                    if line.rstrip().startswith(prefix):
                        suffix = line[len(prefix) + 1:].rstrip()
                        if suffix not in replacements:
                            raise ValueError(
                                f"Expected replacement for '{prefix} {suffix}' "
                                f"not found in {dockerfile}:{line_no}"
                            )

        for prefix, contents in replacements.items():
            blockinfile(
                filename=dockerfile,
                contents=contents,
                prefix=prefix,
            )


def blockinfile(
    filename: str | os.PathLike,
    contents: str, prefix: str | None = None,
    *,
    comment: str = "#",
) -> None:
    """This is similar to the functions in
    * https://homely.readthedocs.io/en/latest/ref/files.html#homely-files-blockinfile-1
    * ansible.modules.lineinfile
    """
    begin_marker = f"{comment * 3} BEGIN{" " + prefix if prefix else ""}"
    end_marker = f"{comment * 3} END{" " + prefix if prefix else ""}"

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


if __name__ == "__main__":
    main()


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

    def test_dry_run(self, fs: FakeFilesystem):
        fs.add_real_directory(source_path=ROOT_DIR / "jupyter", read_only=False)
        fs.add_real_directory(source_path=ROOT_DIR / "codeserver", read_only=False)
        fs.add_real_directory(source_path=ROOT_DIR / "rstudio", read_only=False)
        fs.add_real_directory(source_path=ROOT_DIR / "runtimes", read_only=False)
        main()
