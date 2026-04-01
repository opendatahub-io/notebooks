from __future__ import annotations

import logging

logging.basicConfig(level=logging.DEBUG)

# Exclude tests/containers from default collection (see pytest.ini near testpaths).
# Rationale: heavy third-party imports at collection time; run that subtree explicitly
# with pytest tests/containers when you need it.
#
# This must be set here: pytest.ini has no supported collect_ignore key (pytest 9+
# warns if you add one). conftest collect_ignore paths are relative to this file's
# directory, so "containers" means tests/containers/.
collect_ignore = ["containers"]
