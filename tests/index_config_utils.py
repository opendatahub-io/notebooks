from __future__ import annotations

import configparser
import shlex
import tomllib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PYPI_SIMPLE_INDEX = "https://pypi.org/simple"


def normalize_index_url(url: str) -> str:
    return url.rstrip("/")


def is_pypi_index_url(url: str) -> bool:
    return normalize_index_url(url) == PYPI_SIMPLE_INDEX


def index_urls_are_all_pypi(urls: Sequence[str]) -> bool:
    return all(is_pypi_index_url(url) for url in urls)


def _split_index_values(value: str) -> tuple[str, ...]:
    return tuple(token.strip() for token in shlex.split(value) if token.strip())


def pip_index_url_from_config(config_text: str) -> str | None:
    parser = configparser.ConfigParser()
    parser.read_string(config_text)
    value = parser.get("global", "index-url", fallback=None)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def pip_all_index_urls_from_config(config_text: str) -> tuple[str, ...]:
    parser = configparser.ConfigParser()
    parser.read_string(config_text)
    urls: list[str] = []
    for option in ("index-url", "extra-index-url"):
        value = parser.get("global", option, fallback=None)
        if value is not None:
            urls.extend(_split_index_values(value))
    return tuple(urls)


def uv_index_url_from_config(config_text: str) -> str | None:
    data = tomllib.loads(config_text)
    value = data.get("index-url")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def uv_all_index_urls_from_config(config_text: str) -> tuple[str, ...]:
    data = tomllib.loads(config_text)
    urls: list[str] = []
    for option in ("index-url", "default-index"):
        value = data.get(option)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                urls.append(normalized)

    for entry in data.get("index", []):
        if isinstance(entry, dict):
            value = entry.get("url")
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    urls.append(normalized)

    return tuple(urls)


def env_index_urls(env: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    urls: dict[str, tuple[str, ...]] = {}
    for key in ("PIP_INDEX_URL", "UV_INDEX_URL", "UV_DEFAULT_INDEX"):
        value = env.get(key)
        if value:
            urls[key] = (value,)

    for key in ("PIP_EXTRA_INDEX_URL", "UV_EXTRA_INDEX_URL"):
        value = env.get(key)
        if value:
            urls[key] = _split_index_values(value)

    value = env.get("UV_INDEX")
    if value:
        uv_indexes = []
        for token in _split_index_values(value):
            _name, separator, url = token.partition("=")
            uv_indexes.append(url if separator else token)
        urls["UV_INDEX"] = tuple(index for index in uv_indexes if index)

    return urls
