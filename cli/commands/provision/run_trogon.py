#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Trogon: Auto-generated TUI from CLI commands.

Run with: uv run --with typer --with trogon python cli/commands/provision/run_trogon.py

USAGE:
  # Normal CLI mode (with autocomplete):
  python run_trogon.py create my-instance --zone us-central1-a
  python run_trogon.py --help

  # Launch the TUI:
  python run_trogon.py tui

HOW TO USE THE TUI:
  1. Press ^t (Ctrl+T) to focus the command tree on the left
  2. Use arrow keys to expand/navigate commands (create, bootstrap, check, etc.)
  3. Press Enter to select a command - form fields appear on the right
  4. Fill in the form fields
  5. Press ^r (Ctrl+R) to run the command
  
KEYBOARD SHORTCUTS:
  ^t  Focus Command Tree (navigate with arrows)
  ^r  Close & Run (execute the command)
  ^s  Search commands
  ^p  Command palette
  q   Quit
"""

import typer
from rich.console import Console
from rich.panel import Panel

# Try to import trogon
try:
    from trogon import Trogon
    TROGON_AVAILABLE = True
except ImportError:
    TROGON_AVAILABLE = False

console = Console()

# Machine types
MACHINE_TYPES = ["e2-small", "e2-medium", "e2-standard-2", "e2-standard-4", "n1-standard-4"]
ZONES = ["us-central1-a", "us-central1-b", "us-east1-b", "us-west1-a", "europe-west1-b"]
BLOCKED_MACHINE_TYPES = {"e2-micro", "f1-micro", "g1-small"}

app = typer.Typer(
    name="provision",
    help="GCP instance provisioning with sane defaults for notebook development.",
    no_args_is_help=True,
)


def machine_type_callback(value: str) -> str:
    """Validate machine type."""
    if value in BLOCKED_MACHINE_TYPES:
        raise typer.BadParameter(
            f"Machine type '{value}' is blocked. Too small for development. "
            f"Use one of: {', '.join(MACHINE_TYPES)}"
        )
    return value


@app.command("create")
def create_instance(
    name: str = typer.Argument(..., help="Instance name (e.g., my-notebook)"),
    zone: str = typer.Option(
        "us-central1-a",
        "--zone", "-z",
        help="GCP zone",
        autocompletion=lambda: ZONES,
    ),
    machine_type: str = typer.Option(
        "e2-medium",
        "--machine-type", "-m",
        help="Machine type (e2-micro blocked)",
        autocompletion=lambda: MACHINE_TYPES,
        callback=machine_type_callback,
    ),
    swap_gb: int = typer.Option(
        4,
        "--swap", "-s",
        help="Swap file size in GB (1-16)",
        min=1,
        max=16,
    ),
    optimize_dnf: bool = typer.Option(
        True,
        "--optimize-dnf/--no-optimize-dnf",
        help="Disable debug/source repos, optimize metadata",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run", "-n",
        help="Show what would be done without executing",
    ),
):
    """
    Create a GCP instance with sane defaults.
    
    Automatically configures:
    • Swap file (prevents OOM during DNF operations)
    • DNF optimization (disables debug/source repos)
    • Blocks e2-micro (too small for development)
    
    Examples:
        provision create my-notebook
        provision create my-notebook --zone us-west1-a --machine-type e2-standard-2
        provision create my-notebook --swap 8 --no-optimize-dnf
    """
    from command import generate_startup_script
    
    console.print(Panel(
        f"[bold green]Creating instance:[/bold green] {name}\n"
        f"Zone: {zone}\n"
        f"Machine: {machine_type}\n"
        f"Swap: {swap_gb}GB\n"
        f"DNF Optimization: {'✓' if optimize_dnf else '✗'}",
        title="Configuration",
    ))
    
    if dry_run:
        startup_script = generate_startup_script(swap_gb, optimize_dnf)
        console.print("\n[yellow]Dry run - would execute:[/yellow]")
        console.print(f"[dim]{startup_script[:500]}...[/dim]")
        return
    
    console.print("\n[bold]Would run: gcloud compute instances create ...[/bold]")


@app.command("bootstrap")
def bootstrap_existing(
    name: str = typer.Argument(..., help="Existing instance name"),
    zone: str = typer.Option(
        "us-central1-a",
        "--zone", "-z",
        help="GCP zone",
        autocompletion=lambda: ZONES,
    ),
    swap_gb: int = typer.Option(4, "--swap", "-s", help="Swap size in GB"),
):
    """
    Bootstrap an existing instance with swap and DNF optimizations.
    
    Use this for instances created without the startup script.
    """
    console.print(f"[bold]Bootstrapping {name} in {zone}...[/bold]")
    console.print(f"Would configure {swap_gb}GB swap and optimize DNF.")


@app.command("check")
def check_instance(
    name: str = typer.Argument(..., help="Instance name to check"),
    zone: str = typer.Option(
        "us-central1-a",
        "--zone", "-z",
        autocompletion=lambda: ZONES,
    ),
):
    """Check instance configuration (swap, DNF, machine type)."""
    console.print(f"[bold]Checking {name} in {zone}...[/bold]")


@app.command("list-zones")
def list_zones():
    """List available GCP zones."""
    console.print("[bold]Available zones:[/bold]")
    for zone in ZONES:
        console.print(f"  • {zone}")


@app.command("list-machines")
def list_machines():
    """List recommended machine types."""
    console.print("[bold]Recommended machine types:[/bold]")
    for machine in MACHINE_TYPES:
        console.print(f"  • {machine}")
    console.print("\n[yellow]Blocked (too small):[/yellow]")
    for machine in BLOCKED_MACHINE_TYPES:
        console.print(f"  • {machine} ⚠️")


# Add Trogon TUI command if available
if TROGON_AVAILABLE:
    @app.command("tui")
    def launch_trogon_tui(ctx: typer.Context):
        """
        Launch interactive TUI.
        
        Navigate with arrow keys, fill forms, run commands visually.
        Press ^t to focus command tree, ^r to run.
        
        Known issue: ^o crashes if no command selected - just ignore that key.
        """
        # Get the parent Click context to pass to Trogon
        click_ctx = ctx
        while click_ctx.parent:
            click_ctx = click_ctx.parent
        Trogon(
            app,
            click_context=click_ctx,
            app_name="provision",
        ).run()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    """
    GCP Instance Provisioning CLI.
    
    Create and manage GCP instances with sane defaults for notebook development.
    """
    if version:
        console.print("provision v0.1.0")
        raise typer.Exit()


if __name__ == "__main__":
    app()
