#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Standalone CLI runner with shell autocompletion support.

Run with: uv run --with typer python cli/commands/provision/run_cli.py --help

Enable shell autocompletion:
  # For bash
  uv run --with typer python cli/commands/provision/run_cli.py --install-completion bash
  
  # For zsh
  uv run --with typer python cli/commands/provision/run_cli.py --install-completion zsh
  
  # For fish
  uv run --with typer python cli/commands/provision/run_cli.py --install-completion fish

After installing, restart your shell and try:
  python run_cli.py create <TAB>
  python run_cli.py create my-instance --zone <TAB>
"""

from command import app

if __name__ == "__main__":
    app()
