from __future__ import annotations

from tests.index_config_utils import is_pypi_index_url, pip_index_url_from_config, uv_index_url_from_config


def test_pip_index_url_from_config_reads_global_index_url():
    config_text = """# pip.conf
[global]
index-url = https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/
"""

    assert (
        pip_index_url_from_config(config_text)
        == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    )


def test_uv_index_url_from_config_reads_index_url():
    config_text = """# uv.toml
index-url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
native-tls = true
"""

    assert (
        uv_index_url_from_config(config_text)
        == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    )


def test_is_pypi_index_url_normalizes_trailing_slash():
    assert is_pypi_index_url("https://pypi.org/simple")
    assert is_pypi_index_url("https://pypi.org/simple/")
    assert not is_pypi_index_url("https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/")
