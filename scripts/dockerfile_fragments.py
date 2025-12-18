#!/usr/bin/env python3

"""
This script is inspired by the AIPCC `replace-markers.sh` script, invoked from `make regen`
  https://gitlab.com/redhat/rhel-ai/core/base-images/app/-/blob/main/containerfiles/replace-markers.sh

The original AIPCC version uses the `ed` command to replace everything between
 `### BEGIN <filename>` and `### END <filename>` with the content of the <filename>.

This script currently has the data inline, but this can be easily changed.
We could also support files, or maybe even `### BEGIN funcname("param1", "param2")` that would
 run Python function `funcname` and paste in the return value.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import ntb

if TYPE_CHECKING:
    import pathlib

    from pyfakefs.fake_filesystem import FakeFilesystem

# restricting to the relevant directories significantly speeds up the processing
docker_directories = (
    ntb.ROOT_DIR / "jupyter",
    ntb.ROOT_DIR / "codeserver",
    ntb.ROOT_DIR / "rstudio",
    ntb.ROOT_DIR / "runtimes",
)


def sanity_check(dockerfile: pathlib.Path, replacements: dict[str, str]):
    """Sanity check that we don't have any unexpected `### BEGIN`s and `### END`s"""
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


def main():
    subscription_manager_register_refresh = textwrap.dedent(r"""
        # If we have a Red Hat subscription prepared, refresh it
        RUN /bin/bash <<'EOF'
        set -Eeuxo pipefail
        if command -v subscription-manager &> /dev/null; then
          subscription-manager identity &>/dev/null && subscription-manager refresh || echo "No identity, skipping refresh."
        fi
        EOF
    """)

    replacements = {
        "RHAIENG-2189: this is AIPCC migration phase 1.5": textwrap.dedent(r"""
            ENV PIP_INDEX_URL=https://pypi.org/simple
            # UV_INDEX_URL is deprecated in favor of UV_DEFAULT_INDEX
            ENV UV_INDEX_URL=https://pypi.org/simple
            # https://docs.astral.sh/uv/reference/environment/#uv_default_index
            ENV UV_DEFAULT_INDEX=https://pypi.org/simple"""),

        "Subscribe with subscription manager": textwrap.dedent(subscription_manager_register_refresh),
        "upgrade first to avoid fixable vulnerabilities": textwrap.dedent(ntb.process_template_with_indents(rt"""
            {subscription_manager_register_refresh}
            # Problem: The operation would result in removing the following protected packages: systemd
            #  (try to add '--allowerasing' to command line to replace conflicting packages or '--skip-broken' to skip uninstallable packages)
            # Solution: --best --skip-broken does not work either, so use --nobest
            RUN /bin/bash <<'EOF'
            set -Eeuxo pipefail
            dnf -y upgrade --refresh --nobest --skip-broken --nodocs --noplugins --setopt=install_weak_deps=0 --setopt=keepcache=0
            dnf clean all -y
            EOF

        """)),
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

    for docker_dir in docker_directories:
        for dockerfile in docker_dir.glob("**/Dockerfile*"):
            if not dockerfile.is_file():
                continue
            if dockerfile.is_relative_to(ntb.ROOT_DIR / "base-images"):
                continue
            if dockerfile.is_relative_to(ntb.ROOT_DIR / "examples"):
                continue

            sanity_check(dockerfile, replacements)

            for prefix, contents in replacements.items():
                ntb.blockinfile(
                    filename=dockerfile,
                    contents=contents,
                    prefix=prefix,
                )


if __name__ == "__main__":
    main()


class TestMain:
    def test_dry_run(self, fs: FakeFilesystem):
        for docker_dir in docker_directories:
            fs.add_real_directory(source_path=docker_dir, read_only=False)
        main()
