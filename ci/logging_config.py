"""Shared structured logging configuration using structlog.

Usage:
    from ci.logging_config import configure_logging
    configure_logging()

    import structlog
    log = structlog.get_logger()
    log.info("Processing image", target="minimal", variant="cpu")

    # t-strings (Python 3.14+) auto-extract structured keys:
    log.info(t"Processing {filepath}")  # adds filepath=... to event dict
"""

from __future__ import annotations

import logging
import os
from string import templatelib
from string.templatelib import Interpolation, Template

import structlog


def _render_template(template: Template) -> str:
    """Render a Template to a plain string, applying format specs."""
    parts: list[str] = []
    for part in template:
        if isinstance(part, Interpolation):
            value = templatelib.convert(part.value, part.conversion)
            parts.append(format(value, part.format_spec))
        else:
            parts.append(part)
    return "".join(parts)


def t_string_processor(logger: object, method_name: str, event_dict: dict) -> dict:
    """Extract structured keys from t-string Template events.

    When a log call uses a t-string (e.g. ``log.info(t"User {user_id}")``),
    the event is a ``Template`` object.  This processor extracts each
    interpolated expression as a key-value pair in the event dict, then
    renders the template to a plain string for the ``event`` field.

    Explicitly passed kwargs take precedence over auto-extracted values.
    """
    event = event_dict.get("event")
    if isinstance(event, Template):
        for part in event:
            if isinstance(part, Interpolation):
                event_dict.setdefault(part.expression, part.value)
        event_dict["event"] = _render_template(event)
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool | None = None) -> None:
    """Configure structlog with stdlib integration.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, render JSON lines; if False, render colorized
            human-readable output.  None (default) auto-detects: JSON when
            the ``CI`` environment variable is set, human-readable otherwise.
    """
    if json_output is None:
        json_output = bool(os.environ.get("CI"))

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        t_string_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
