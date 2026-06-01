from __future__ import annotations

import configparser
import tomllib

PYPI_SIMPLE_INDEX = "https://pypi.org/simple"


def normalize_index_url(url: str) -> str:
    return url.rstrip("/")


def is_pypi_index_url(url: str) -> bool:
    return normalize_index_url(url) == PYPI_SIMPLE_INDEX


def pip_index_url_from_config(config_text: str) -> str | None:
    parser = configparser.ConfigParser()
    parser.read_string(config_text)
    value = parser.get("global", "index-url", fallback=None)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def uv_index_url_from_config(config_text: str) -> str | None:
    data = tomllib.loads(config_text)
    value = data.get("index-url")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
