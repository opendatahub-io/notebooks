#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def validate_json_file(filepath: Path) -> bool:
    """Validates the JSON syntax of a single file.
    Returns True if valid, False otherwise.
    """
    print(f"Checking: '{filepath}'")
    try:
        with filepath.open("r", encoding="utf-8") as f:
            json.load(f)
        print("  > OK")
        return True
    except json.JSONDecodeError as e:
        # Print specific error for easier debugging
        print(f"  > Invalid JSON: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"  > Error reading file: {e}", file=sys.stderr)
        return False


def main():
    """Recursively finds and validates all specified JSON-like files in the project."""
    # Define file patterns to search for, relative to the current directory
    file_patterns = [
        "**/*.json",
        "**/*.ipynb",
    ]

    # Define a set of file names to exclude from validation
    exclude_filenames = {
        "tsconfig.json",
    }

    print("--- Starting JSON syntax validation ---")
    root_dir = Path(".")
    errors: list[Path] = []

    # Create a set to hold unique file paths, preventing duplicate checks
    files_to_validate = set()
    for pattern in file_patterns:
        print(f"-- Searching for '{pattern}' files...")
        files_to_validate.update(root_dir.glob(pattern))

    if not files_to_validate:
        print("\nNo files found to validate.")
        sys.exit(0)

    # Sort files for consistent, readable output
    for filepath in sorted(files_to_validate):
        if filepath.name in exclude_filenames:
            print(f"Skipping excluded file: {filepath}")
            continue

        if not validate_json_file(filepath):
            errors.append(filepath)

    print("\n--- Validation finished ---")
    if errors:
        print("\nError: Invalid JSON found in one or more files:", file=sys.stderr)
        print(*errors, sep="\n", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nSuccess: All checked files have valid JSON syntax.")
        sys.exit(0)


if __name__ == "__main__":
    main()
