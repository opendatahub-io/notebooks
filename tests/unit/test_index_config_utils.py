from __future__ import annotations

from tests.index_config_utils import (
    env_index_urls,
    index_urls_are_all_pypi,
    is_pypi_index_url,
    pip_all_index_urls_from_config,
    pip_index_url_from_config,
    uv_all_index_urls_from_config,
    uv_index_url_from_config,
)


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


def test_pip_all_index_urls_from_config_reads_primary_and_extra_indexes():
    config_text = """# pip.conf
[global]
index-url = https://pypi.org/simple
extra-index-url =
    https://packages.example.invalid/simple/
    https://mirror.example.invalid/simple/
"""

    assert pip_all_index_urls_from_config(config_text) == (
        "https://pypi.org/simple",
        "https://packages.example.invalid/simple/",
        "https://mirror.example.invalid/simple/",
    )


def test_uv_all_index_urls_from_config_reads_primary_and_named_indexes():
    config_text = """# uv.toml
index-url = "https://pypi.org/simple"
default-index = "https://mirror.example.invalid/simple/"
[[index]]
name = "private"
url = "https://packages.example.invalid/simple/"
"""

    assert uv_all_index_urls_from_config(config_text) == (
        "https://pypi.org/simple",
        "https://mirror.example.invalid/simple/",
        "https://packages.example.invalid/simple/",
    )


def test_env_index_urls_collects_extra_and_named_uv_indexes():
    env = {
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "PIP_EXTRA_INDEX_URL": "https://packages.example.invalid/simple/",
        "UV_EXTRA_INDEX_URL": (
            "https://packages.example.invalid/simple/ https://mirror.example.invalid/simple/"
        ),
        "UV_INDEX": "private=https://packages.example.invalid/simple/ https://pypi.org/simple",
    }

    assert env_index_urls(env) == {
        "PIP_INDEX_URL": ("https://pypi.org/simple",),
        "PIP_EXTRA_INDEX_URL": ("https://packages.example.invalid/simple/",),
        "UV_EXTRA_INDEX_URL": (
            "https://packages.example.invalid/simple/",
            "https://mirror.example.invalid/simple/",
        ),
        "UV_INDEX": (
            "https://packages.example.invalid/simple/",
            "https://pypi.org/simple",
        ),
    }


def test_index_urls_are_all_pypi_rejects_non_pypi_indexes():
    assert index_urls_are_all_pypi(("https://pypi.org/simple", "https://pypi.org/simple/"))
    assert not index_urls_are_all_pypi(
        (
            "https://pypi.org/simple",
            "https://packages.example.invalid/simple/",
        )
    )
