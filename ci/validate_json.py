#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import structlog

from ci.logging_config import configure_logging

log = structlog.get_logger()


def validate_json_file(filepath: Path) -> bool:
    """Validates the JSON syntax of a single file.
    Returns True if valid, False otherwise.
    """
    log.info(f"Checking: '{filepath}'")
    try:
        with filepath.open("r", encoding="utf-8") as f:
            json.load(f)
        log.info("  > OK")
        return True
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in {filepath}: {e}")
        return False
    except OSError as e:
        log.error(f"Error reading file {filepath}: {e}")
        return False


def main():
    """Recursively finds and validates all specified JSON-like files in the project."""
    configure_logging()

    # Define file patterns to search for, relative to the current directory
    file_patterns = [
        "**/*.json",
        "**/*.ipynb",
    ]

    # Define a set of file names to exclude from validation
    exclude_filenames = {
        "tsconfig.json",
    }

    log.info("--- Starting JSON syntax validation ---")
    root_dir = Path(".")
    errors: list[Path] = []

    # Create a set to hold unique file paths, preventing duplicate checks
    files_to_validate = set()
    for pattern in file_patterns:
        log.info(f"Searching for '{pattern}' files...")
        files_to_validate.update(root_dir.glob(pattern))

    if not files_to_validate:
        log.info("No files found to validate.")
        sys.exit(0)

    # Sort files for consistent, readable output
    for filepath in sorted(files_to_validate):
        if filepath.name in exclude_filenames:
            log.info(f"Skipping excluded file: {filepath}")
            continue

        if not validate_json_file(filepath):
            errors.append(filepath)

    log.info("--- Validation finished ---")
    if errors:
        log.error(f"Invalid JSON found in {len(errors)} file(s): {errors}")
        sys.exit(1)
    else:
        log.info("Success: All checked files have valid JSON syntax.")
        sys.exit(0)


if __name__ == "__main__":
    main()
