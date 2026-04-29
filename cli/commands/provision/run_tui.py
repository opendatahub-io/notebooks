#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Standalone runner for the Textual TUI (for testing without full CLI setup)."""

# Run with: uv run --with textual python cli/commands/provision/run_tui.py

from tui import ProvisionApp

if __name__ == "__main__":
    app = ProvisionApp()
    app.run()
