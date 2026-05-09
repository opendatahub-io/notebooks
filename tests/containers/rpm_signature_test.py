"""Validate that RPMs in container images are signed by known Red Hat signing keys.

This test catches non-Red Hat signed RPMs that would be flagged by Konflux
Enterprise Contract post-merge.  It runs ``rpm -qa --qf '%{NAME} %{SIGPGP:pgpsig}\\n'``
inside the image and checks each RPM's signing key against an allowlist.

Five Blocker-level conforma violations went undetected because this check
was missing from PR CI:

- unsigned gpg-pubkey RPM in CODESERVER images
- EPEL-signed RPMs (key ``3228467c``) in CODESERVER images
- NVIDIA-signed RPMs (key ``d42d0685``) in CUDA images
- AMD-signed RPMs (key ``1a693c5c``) in ROCm images
- Microsoft-signed RPMs (key ``be1229cf``) for mssql-tools18

Run explicitly::

    pytest tests/containers/rpm_signature_test.py -v --image=<image>
    pytest tests/containers/ -m manifest_validation -v --image=<image>
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import pytest

from tests.containers import conftest, docker_utils

if TYPE_CHECKING:
    import pytest_subtests

_LOG = logging.getLogger(__name__)

# Known Red Hat GPG signing key IDs (last 8 hex chars of the 64-bit key ID).
_RED_HAT_KEY_IDS: frozenset[str] = frozenset(
    {
        "fd431d51",  # Red Hat, Inc. (release key 2)
        "d4082792",  # Red Hat, Inc. (auxiliary key 3)
        "5a6340b3",  # Red Hat, Inc. (auxiliary key 2)
        "4eb84e71",  # Red Hat, Inc. (release key)
        "2fa658e0",  # Red Hat, Inc. (Product Security)
        "897da07a",  # Red Hat, Inc.
        "8483c65d",  # CentOS Stream (UBI-rebased images)
    }
)

# Non-Red Hat signing key IDs allowed for specific image types.
# Keys are substrings matched against the image reference.
_EXTRA_ALLOWED_KEYS: dict[str, frozenset[str]] = {
    "-cuda-": frozenset({"d42d0685"}),
    "-pytorch-": frozenset({"d42d0685"}),
    "-tensorflow-": frozenset({"d42d0685"}),
    "-rocm-": frozenset({"1a693c5c"}),
}


def _allowed_keys_for_image(image_ref: str) -> frozenset[str]:
    """Return the full set of allowed signing keys for an image type."""
    extra: set[str] = set()
    image_ref = image_ref.lower()
    for pattern, keys in _EXTRA_ALLOWED_KEYS.items():
        if pattern in image_ref:
            extra |= keys
    return _RED_HAT_KEY_IDS | frozenset(extra)


def _parse_key_id(sig_field: str) -> str | None:
    """Extract the 8-char short key ID from an RPM ``%{SIGPGP:pgpsig}`` value.

    Returns ``None`` when the RPM is unsigned (``(none)``).
    """
    if not sig_field or "(none)" in sig_field:
        return None
    m = re.search(r"Key ID\s+([0-9a-fA-F]{16})", sig_field)
    if m:
        return m.group(1)[-8:].lower()
    m = re.search(r"Key ID\s+([0-9a-fA-F]{8})", sig_field)
    if m:
        return m.group(1).lower()
    return None


@pytest.mark.manifest_validation
class TestRpmSignatures:
    def test_rpm_signatures(self, image: str, subtests: pytest_subtests.SubTests):
        """Every RPM in the image must be signed by a known Red Hat key (or an allowed vendor key)."""
        image_metadata = conftest.get_image_metadata(image)
        image_name = image_metadata.labels.get("name", "")
        allowed_keys = _allowed_keys_for_image(image)

        _LOG.info(f"Checking RPM signatures for {image} (name label: {image_name!r})")

        with docker_utils.running_container(image) as container:
            ecode, output = container.exec(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}\t%{SIGPGP:pgpsig}\n"])
            assert ecode == 0, f"rpm -qa failed: {output.decode()}"

            unsigned: list[str] = []
            disallowed: list[tuple[str, str]] = []

            for line in output.decode().strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t", 2)
                if len(parts) < 3:
                    continue
                rpm_name, rpm_version, sig_info = parts[0], parts[1], parts[2]

                if rpm_name == "gpg-pubkey":
                    imported_key_id = rpm_version.lower()
                    if imported_key_id not in allowed_keys:
                        disallowed.append((f"{rpm_name}-{rpm_version}", imported_key_id))
                    continue

                key_id = _parse_key_id(sig_info)
                if key_id is None:
                    unsigned.append(rpm_name)
                elif key_id not in allowed_keys:
                    disallowed.append((rpm_name, key_id))

            for rpm_name in unsigned:
                with subtests.test(msg=f"{rpm_name}: unsigned"):
                    pytest.fail(f"RPM {rpm_name} is unsigned")

            for rpm_name, key_id in disallowed:
                with subtests.test(msg=f"{rpm_name}: key {key_id}"):
                    pytest.fail(f"RPM {rpm_name} is signed by non-allowed key {key_id}")
