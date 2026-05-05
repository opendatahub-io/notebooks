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

import re
import textwrap
import tomllib
from typing import TYPE_CHECKING

import ntb

if TYPE_CHECKING:
    import pathlib

    from pyfakefs.fake_filesystem import FakeFilesystem

# Default versions keep current behavior when lockfiles do not include these packages.
DEFAULT_MICROPIPENV_VERSION = "1.10.0"
DEFAULT_UV_VERSION = "0.10.8"
MICROPIPENV_UV_REPLACEMENT_KEY = "Install micropipenv and uv to deploy packages from requirements.txt"
MICROPIPENV_UV_INLINE_LINE_RE = re.compile(
    r'^(?P<prefix>\s*RUN pip install\s+.+?)\s+"micropipenv\[toml\]==[^"]+"\s+"uv==[^"]+"\s*$'
)

# restricting to the relevant directories significantly speeds up the processing
docker_directories = (
    ntb.ROOT_DIR / "base-images",
    ntb.ROOT_DIR / "jupyter",
    ntb.ROOT_DIR / "codeserver",
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



def get_dockerfile_flavor(dockerfile: pathlib.Path) -> str | None:
    """Extract flavor (cpu/cuda/rocm) from a Dockerfile name."""
    for flavor in ("cpu", "cuda", "rocm"):
        if dockerfile.name.endswith(f".{flavor}"):
            return flavor
    return None


def get_lockfile_for_dockerfile(dockerfile: pathlib.Path) -> pathlib.Path | None:
    """Resolve lockfile source according to uv.lock.d/pylock fallback rules."""
    docker_dir = dockerfile.parent
    uv_lock_dir = docker_dir / "uv.lock.d"
    if uv_lock_dir.is_dir():
        flavor = get_dockerfile_flavor(dockerfile)
        if flavor is None:
            return None
        lockfile = uv_lock_dir / f"pylock.{flavor}.toml"
        return lockfile if lockfile.is_file() else None

    lockfile = docker_dir / "pylock.toml"
    return lockfile if lockfile.is_file() else None


def get_package_versions_from_lockfile(lockfile: pathlib.Path | None) -> dict[str, str]:
    """Read package versions from a pylock TOML file."""
    if lockfile is None:
        return {}
    try:
        with open(lockfile, "rb") as fp:
            lock_data = tomllib.load(fp)
    except (OSError, tomllib.TOMLDecodeError):
        return {}

    packages = lock_data.get("packages")
    if not isinstance(packages, list):
        return {}

    versions = {}
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions[name] = version
    return versions


def resolve_micropipenv_uv_versions(
    dockerfile: pathlib.Path,
    *,
    lockfile_cache: dict[pathlib.Path, tuple[str, str]],
) -> tuple[str, str]:
    """Resolve micropipenv/uv versions for one Dockerfile with defaults fallback."""
    lockfile = get_lockfile_for_dockerfile(dockerfile)
    if lockfile is None:
        return DEFAULT_MICROPIPENV_VERSION, DEFAULT_UV_VERSION
    if lockfile in lockfile_cache:
        return lockfile_cache[lockfile]

    package_versions = get_package_versions_from_lockfile(lockfile)
    resolved_versions = (
        package_versions.get("micropipenv", DEFAULT_MICROPIPENV_VERSION),
        package_versions.get("uv", DEFAULT_UV_VERSION),
    )
    lockfile_cache[lockfile] = resolved_versions
    return resolved_versions


def build_micropipenv_uv_install_fragment(micropipenv_version: str, uv_version: str) -> str:
    return (
        'RUN pip install --no-cache-dir --extra-index-url https://pypi.org/simple -U '
        f'"micropipenv[toml]=={micropipenv_version}" "uv=={uv_version}"'
    )


def replace_inline_micropipenv_uv_install_line(
    dockerfile: pathlib.Path,
    micropipenv_version: str,
    uv_version: str,
) -> None:
    """Update unmarked inline RUN pip install lines for micropipenv/uv."""
    with open(dockerfile, "rt") as fp:
        original_lines = fp.readlines()

    updated_lines: list[str] = []
    changed = False
    for line in original_lines:
        match = MICROPIPENV_UV_INLINE_LINE_RE.match(line.rstrip("\n"))
        if match:
            new_line = (
                f'{match.group("prefix")} '
                f'"micropipenv[toml]=={micropipenv_version}" "uv=={uv_version}"\n'
            )
            updated_lines.append(new_line)
            changed = changed or (new_line != line)
            continue
        updated_lines.append(line)

    if changed:
        with open(dockerfile, "wt") as fp:
            fp.writelines(updated_lines)


def main():
    subscription_manager_register_refresh = textwrap.dedent(r"""
        RUN /bin/bash <<'EOF'
        # If we have a Red Hat subscription prepared, refresh it
        set -Eeuxo pipefail
        if command -v subscription-manager &> /dev/null; then
          subscription-manager identity &>/dev/null && subscription-manager refresh || echo "No identity, skipping refresh."
        fi
        EOF
    """)

    replacements = {
        "AIPCC pip and uv config files": textwrap.dedent(r'''
            ARG INDEX_URL
            COPY --chmod=664 --chown=1001:0 base-images/utils/pip.conf.in /opt/app-root/pip.conf
            COPY --chmod=664 --chown=1001:0 base-images/utils/uv.toml.in /opt/app-root/uv.toml
            RUN /bin/bash <<'EOF'
            set -Eeuxo pipefail
            if [ -z "${INDEX_URL}" ]; then
              echo "ERROR: INDEX_URL build arg is required" >&2
              exit 1
            fi
            sed -i "s|@INDEX_URL@|${INDEX_URL}|g" /opt/app-root/pip.conf
            sed -i "s|@INDEX_URL@|${INDEX_URL}|g" /opt/app-root/uv.toml
            EOF

            # Python and virtual env settings
            ENV VIRTUAL_ENV=${APP_ROOT} \
                PIP_CONFIG_FILE=/opt/app-root/pip.conf \
                UV_CONFIG_FILE=/opt/app-root/uv.toml \
                PIP_NO_CACHE_DIR=off \
                UV_NO_CACHE=true \
                PIP_DISABLE_PIP_VERSION_CHECK=1 \
                PYTHONUNBUFFERED=1 \
                PYTHONIOENCODING=utf-8 \
                LANG=en_US.UTF-8 \
                LC_ALL=en_US.UTF-8 \
                PS1="(app-root) \w\$ "'''),
        "RHAIENG-2189: this is AIPCC migration phase 1.5": textwrap.dedent(r"""
            ENV PIP_INDEX_URL=https://pypi.org/simple
            # UV_INDEX_URL is deprecated in favor of UV_DEFAULT_INDEX
            ENV UV_INDEX_URL=https://pypi.org/simple
            # https://docs.astral.sh/uv/reference/environment/#uv_default_index
            ENV UV_DEFAULT_INDEX=https://pypi.org/simple"""),

        "Subscribe with subscription manager": textwrap.dedent(subscription_manager_register_refresh),
        "upgrade first to avoid fixable vulnerabilities": textwrap.dedent(ntb.process_template_with_indents(rt"""
            {subscription_manager_register_refresh}
            RUN --mount=type=bind,source=base-images/utils/dnf-helper.sh,target=/utils/dnf-helper.sh,ro \
                /utils/dnf-helper.sh upgrade

        """)),
        MICROPIPENV_UV_REPLACEMENT_KEY: build_micropipenv_uv_install_fragment(
            micropipenv_version=DEFAULT_MICROPIPENV_VERSION,
            uv_version=DEFAULT_UV_VERSION,
        ),
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

        "mongocli-builder stage": textwrap.dedent(r"""
            ######################################################
            # mongocli-builder (build stage only, not published) #
            ######################################################
            FROM registry.access.redhat.com/ubi9/go-toolset:1.25.8-1776370298 AS mongocli-builder

            ARG MONGOCLI_VERSION=2.0.4

            WORKDIR /tmp/
            RUN /bin/bash <<'EOF'
            set -Eeuxo pipefail
            curl -Lo mongodb-cli-mongocli-v${MONGOCLI_VERSION}.zip https://github.com/mongodb/mongodb-cli/archive/refs/tags/mongocli/v${MONGOCLI_VERSION}.zip
            unzip ./mongodb-cli-mongocli-v${MONGOCLI_VERSION}.zip
            cd ./mongodb-cli-mongocli-v${MONGOCLI_VERSION}/
            CGO_ENABLED=1 GOOS=linux go build -a -tags strictfipsruntime -o /tmp/mongocli ./cmd/mongocli/
            EOF
        """),
        "mongocli-builder stage with s390x support": textwrap.dedent(r"""
            ######################################################
            # mongocli-builder (build stage only, not published) #
            ######################################################
            FROM registry.access.redhat.com/ubi9/go-toolset:1.25.8-1776370298 AS mongocli-builder

            ARG MONGOCLI_VERSION=2.0.4

            WORKDIR /tmp/

            ARG TARGETARCH

            # Keep s390x special-case from original (create dummy binary) but
            # include explicit curl/unzip steps from the delta for non-s390x.
            RUN /bin/bash <<'EOF'
            set -Eeuxo pipefail
            arch="${TARGETARCH:-$(uname -m)}"
            arch=$(echo "$arch" | cut -d- -f1)
            if [ "$arch" = "s390x" ]; then
                echo "Skipping mongocli build for ${arch}, creating dummy binary"
                mkdir -p /tmp && printf '#!/bin/sh\necho "mongocli not supported on s390x"\n' > /tmp/mongocli
                chmod +x /tmp/mongocli
            else
                echo "Building mongocli for ${arch}"
                curl -Lo mongodb-cli-mongocli-v${MONGOCLI_VERSION}.zip https://github.com/mongodb/mongodb-cli/archive/refs/tags/mongocli/v${MONGOCLI_VERSION}.zip
                unzip ./mongodb-cli-mongocli-v${MONGOCLI_VERSION}.zip
                cd ./mongodb-cli-mongocli-v${MONGOCLI_VERSION}/
                CGO_ENABLED=1 GOOS=linux GOARCH=${arch} GO111MODULE=on go build -a -tags strictfipsruntime -o /tmp/mongocli ./cmd/mongocli/
            fi
            EOF
        """),
        "Copy mongocli from builder": textwrap.dedent(r"""
            # Copy dynamically-linked mongocli built in earlier build stage
            COPY --from=mongocli-builder /tmp/mongocli /opt/app-root/bin/"""),
        "Install software and packages": textwrap.dedent(r"""
            echo "Installing software and packages"
            # Install Python packages from lockfile with hash verification
            # All dependencies are explicitly listed in pylock.toml (--no-deps)
            UV_NO_CACHE=true UV_LINK_MODE=copy UV_PREVIEW_FEATURES=pylock uv pip install \
                --strict --no-deps --no-config --no-progress \
                --require-hashes --compile-bytecode --index-strategy=unsafe-best-match \
                --requirements=./pylock.toml"""),
    }
    lockfile_cache: dict[pathlib.Path, tuple[str, str]] = {}

    for docker_dir in docker_directories:
        for dockerfile in docker_dir.glob("**/Dockerfile*"):
            if not dockerfile.is_file():
                continue
            if dockerfile.is_relative_to(ntb.ROOT_DIR / "examples"):
                continue

            micropipenv_version, uv_version = resolve_micropipenv_uv_versions(
                dockerfile,
                lockfile_cache=lockfile_cache,
            )
            dockerfile_replacements = replacements.copy()
            dockerfile_replacements[MICROPIPENV_UV_REPLACEMENT_KEY] = build_micropipenv_uv_install_fragment(
                micropipenv_version=micropipenv_version,
                uv_version=uv_version,
            )

            sanity_check(dockerfile, dockerfile_replacements)

            for prefix, contents in dockerfile_replacements.items():
                ntb.blockinfile(
                    filename=dockerfile,
                    contents=contents,
                    prefix=prefix,
                )
            replace_inline_micropipenv_uv_install_line(
                dockerfile=dockerfile,
                micropipenv_version=micropipenv_version,
                uv_version=uv_version,
            )


if __name__ == "__main__":
    main()


class TestMain:
    def test_dry_run(self, fs: FakeFilesystem):
        for docker_dir in docker_directories:
            fs.add_real_directory(source_path=docker_dir, read_only=False)
        main()


class TestVersionResolution:
    def test_prefers_uv_lock_variant_when_uv_lock_dir_exists(self, fs: FakeFilesystem):
        dockerfile = ntb.ROOT_DIR / "tmp/test/ubi9-python-3.12/Dockerfile.cpu"
        fs.create_file(dockerfile, contents="")
        fs.create_file(
            dockerfile.parent / "uv.lock.d/pylock.cpu.toml",
            contents="""
[[packages]]
name = "micropipenv"
version = "9.9.9"

[[packages]]
name = "uv"
version = "0.99.0"
""",
        )
        fs.create_file(
            dockerfile.parent / "pylock.toml",
            contents="""
[[packages]]
name = "micropipenv"
version = "1.1.1"

[[packages]]
name = "uv"
version = "0.11.1"
""",
        )

        assert resolve_micropipenv_uv_versions(dockerfile, lockfile_cache={}) == ("9.9.9", "0.99.0")

    def test_uses_top_level_pylock_when_no_uv_lock_dir(self, fs: FakeFilesystem):
        dockerfile = ntb.ROOT_DIR / "tmp/runtime/ubi9-python-3.12/Dockerfile.cpu"
        fs.create_file(dockerfile, contents="")
        fs.create_file(
            dockerfile.parent / "pylock.toml",
            contents="""
[[packages]]
name = "micropipenv"
version = "2.2.2"

[[packages]]
name = "uv"
version = "0.22.2"
""",
        )

        assert resolve_micropipenv_uv_versions(dockerfile, lockfile_cache={}) == ("2.2.2", "0.22.2")

    def test_falls_back_to_defaults_when_packages_are_missing(self, fs: FakeFilesystem):
        dockerfile = ntb.ROOT_DIR / "tmp/defaults/ubi9-python-3.12/Dockerfile.cpu"
        fs.create_file(dockerfile, contents="")
        fs.create_file(
            dockerfile.parent / "pylock.toml",
            contents="""
[[packages]]
name = "setuptools"
version = "80.0.0"
""",
        )

        assert resolve_micropipenv_uv_versions(dockerfile, lockfile_cache={}) == (
            DEFAULT_MICROPIPENV_VERSION,
            DEFAULT_UV_VERSION,
        )


class TestInlineMicropipenvUvLineReplacement:
    def test_replaces_unmarked_inline_line_preserving_flags(self, fs: FakeFilesystem):
        dockerfile = ntb.ROOT_DIR / "tmp/codeserver/ubi9-python-3.12/Dockerfile.cpu"
        fs.create_file(
            dockerfile,
            contents=(
                'RUN pip install --no-cache-dir --no-index --find-links /cachi2/output/deps/pip '
                '"micropipenv[toml]==1.10.0" "uv==0.11.8"\n'
            ),
        )

        replace_inline_micropipenv_uv_install_line(
            dockerfile=dockerfile,
            micropipenv_version="1.10.0",
            uv_version="0.10.12",
        )

        with open(dockerfile, "rt") as fp:
            assert fp.read().strip() == (
                'RUN pip install --no-cache-dir --no-index --find-links /cachi2/output/deps/pip '
                '"micropipenv[toml]==1.10.0" "uv==0.10.12"'
            )

    def test_does_not_fallback_to_pylock_toml_when_uv_lock_dir_exists(self, fs: FakeFilesystem):
        dockerfile = ntb.ROOT_DIR / "tmp/konflux/ubi9-python-3.12/Dockerfile.konflux.cuda"
        fs.create_file(dockerfile, contents="")
        fs.create_dir(dockerfile.parent / "uv.lock.d")
        fs.create_file(
            dockerfile.parent / "pylock.toml",
            contents="""
[[packages]]
name = "micropipenv"
version = "7.7.7"

[[packages]]
name = "uv"
version = "0.77.0"
""",
        )

        assert resolve_micropipenv_uv_versions(dockerfile, lockfile_cache={}) == (
            DEFAULT_MICROPIPENV_VERSION,
            DEFAULT_UV_VERSION,
        )
