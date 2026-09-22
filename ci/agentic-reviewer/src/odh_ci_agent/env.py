"""Shared environment-variable helpers."""

from __future__ import annotations

import os

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise SystemExit(f"Missing required environment variable: {name}")


def bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL
