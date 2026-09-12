from __future__ import annotations

from scripts.ci import validate_renovate_config


def test_repo_renovate_json5_passes_semantic_validation() -> None:
    config = validate_renovate_config.load_config(validate_renovate_config.DEFAULT_CONFIG)
    errors = validate_renovate_config.validate_config(config)
    assert errors == [], f"Expected no semantic validation errors, got: {errors}"
