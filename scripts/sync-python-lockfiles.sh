#!/usr/bin/env bash
set -Eeuxo pipefail

# Red Hat's build tooling depends on requirements.txt files with hashes
# Namely, Konflux (https://konflux-ci.dev/), and Cachi2 (https://github.com/containerbuildsystem/cachi2).

# The following will create a pylock.toml file for every pyproject.toml we have.
uv --version || pip install "uv==0.8.12"
find . -name pylock.toml -execdir bash -c '
  pwd
  # derives python-version from directory suffix (e.g., "ubi9-python-3.12")
  uv pip compile pyproject.toml \
   --output-file pylock.toml \
   --format pylock.toml \
   --generate-hashes \
   --emit-index-url \
   --python-version="${PWD##*-}" \
   --python-platform linux \
   --no-annotate \
   --quiet' \;
