"""Unit tests for the manifest validation registry backends."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from contextlib import nullcontext
from email.message import Message
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.containers import manifest_validation_test as validation


def test_packages_from_sbom_can_keep_manifest_list_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    image_ref = "quay.io/example/image@sha256:index"
    run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"packages": []}', ""))
    monkeypatch.setattr(validation.subprocess, "run", run)
    monkeypatch.setattr(validation, "_resolve_amd64", Mock(side_effect=AssertionError("must not resolve")))
    monkeypatch.setattr(validation, "_enrich_rocm_version_from_image_config", Mock())

    assert validation._packages_from_sbom(image_ref, resolve_amd64=False) == {}
    assert run.call_args.args[0] == ["cosign", "download", "sbom", image_ref]


def test_fetch_quay_security_data_retries_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.read.return_value = json.dumps({"status": "success"}).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    error = urllib.error.HTTPError("https://quay.io", 520, "origin error", Message(), None)
    urlopen = Mock(side_effect=[error, response])
    monkeypatch.setattr(validation.urllib.request, "urlopen", urlopen)
    sleep = Mock()
    monkeypatch.setattr(validation.time, "sleep", sleep)

    assert validation._fetch_quay_security_data(urllib.request.Request("https://quay.io")) == {"status": "success"}
    assert urlopen.call_count == 2
    sleep.assert_called_once_with(1)


def test_fetch_quay_security_data_does_not_retry_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError("https://quay.io", 401, "unauthorized", Message(), None)
    urlopen = Mock(side_effect=error)
    monkeypatch.setattr(validation.urllib.request, "urlopen", urlopen)
    sleep = Mock()
    monkeypatch.setattr(validation.time, "sleep", sleep)

    with pytest.raises(urllib.error.HTTPError, match="401"):
        validation._fetch_quay_security_data(urllib.request.Request("https://quay.io"))

    assert urlopen.call_count == 1
    sleep.assert_not_called()


def test_clair_failed_scan_falls_back_to_sbom(monkeypatch: pytest.MonkeyPatch) -> None:
    tag = validation._TagInfo(
        is_name="jupyter-minimal-notebook-imagestream.yaml",
        tag_name="3.6",
        image_ref="quay.io/example/image@sha256:index",
        python_deps=[{"name": "JupyterLab", "version": "4.5"}],
        software=[],
    )
    subtests = Mock()
    subtests.test.return_value = nullcontext()
    compare = Mock()
    monkeypatch.setattr(validation, "_get_quay_auth", lambda: "auth")
    monkeypatch.setattr(validation.shutil, "which", lambda _: "/usr/bin/skopeo")
    monkeypatch.setattr(validation, "_iter_old_tags", lambda _: [tag])
    monkeypatch.setattr(
        validation,
        "_packages_from_quay",
        Mock(side_effect=validation._ClairScanFailedError("scan failed")),
    )
    sbom = Mock(return_value={"jupyterlab": "4.5.0"})
    monkeypatch.setattr(validation, "_packages_from_sbom", sbom)
    monkeypatch.setattr(validation, "_compare_manifest_vs_actual", compare)

    validation.test_old_tag_annotations_match_quay(subtests, Path("manifests/odh/base"))

    sbom.assert_called_once_with(tag.image_ref, source_hint="/jupyter/minimal/", python_version="")
    assert compare.call_count == 2


def test_code_server_sbom_without_package_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    tag = validation._TagInfo(
        "code-server-notebook-imagestream.yaml", "3.6", "quay.io/example/image@sha256:index", [], []
    )
    subtests = Mock()
    subtests.test.return_value = nullcontext()
    monkeypatch.setattr(validation, "_packages_from_sbom", lambda *args, **kwargs: {})

    with pytest.raises(pytest.skip.Exception, match="not present in the SBOM"):
        validation._validate_code_server_via_sbom(
            subtests,
            tag,
            [{"name": "code-server", "version": "4.122"}],
            has_cosign=True,
        )


def test_code_server_sbom_fetch_failure_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    tag = validation._TagInfo(
        "code-server-notebook-imagestream.yaml", "3.6", "quay.io/example/image@sha256:index", [], []
    )
    subtests = Mock()
    subtests.test.return_value = nullcontext()
    monkeypatch.setattr(validation, "_packages_from_sbom", Mock(side_effect=RuntimeError("no sbom attached")))

    with pytest.raises(pytest.skip.Exception, match="SBOM unavailable"):
        validation._validate_code_server_via_sbom(
            subtests,
            tag,
            [{"name": "code-server", "version": "4.122"}],
            has_cosign=True,
        )
