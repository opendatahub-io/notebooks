from __future__ import annotations

import logging

import pytest

# Enable pytest assertion introspection for the ntb helper module.
# Without this, assert failures in ntb.asserts (e.g. assert_subdict) show a
# bare "AssertionError" with no diff — pytest only rewrites assertions in
# modules it discovers as test files, not in imported utility modules.
# https://github.com/pytest-dev/pytest/issues/1871
# https://github.com/pytest-dev/pytest/issues/3454
pytest.register_assert_rewrite("ntb.asserts")

logging.basicConfig(level=logging.DEBUG)

# Exclude tests/containers from default collection (see pytest.ini near testpaths).
# Rationale: heavy third-party imports at collection time; run that subtree explicitly
# with pytest tests/containers when you need it.
#
# This must be set here: pytest.ini has no supported collect_ignore key (pytest 9+
# warns if you add one). conftest collect_ignore paths are relative to this file's
# directory, so "containers" means tests/containers/.
collect_ignore = ["containers"]
