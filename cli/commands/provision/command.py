# SPDX-License-Identifier: Apache-2.0
"""GCP provisioning CLI commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional

app = typer.Typer(
    name="provision",
    help="GCP instance provisioning with sane defaults for notebook development.",
)
console = Console()

# Machine types that are too small for development work
BLOCKED_MACHINE_TYPES = {"e2-micro", "f1-micro", "g1-small"}

# Recommended minimums
RECOMMENDED_MACHINES = {
    "light": "e2-small",      # 2GB RAM - minimal testing
    "dev": "e2-medium",       # 4GB RAM - development
    "build": "e2-standard-2", # 8GB RAM - container builds
    "ml": "n1-standard-4",    # 15GB RAM - ML workloads
}


@app.command("create")
def create_instance(
    name: str = typer.Argument(..., help="Instance name"),
    zone: str = typer.Option("us-central1-a", "--zone", "-z", help="GCP zone"),
    machine_type: str = typer.Option(
        "e2-small",
        "--machine-type", "-m",
        help="Machine type (e2-micro blocked by default)",
    ),
    swap_gb: int = typer.Option(4, "--swap", "-s", help="Swap file size in GB"),
    optimize_dnf: bool = typer.Option(True, "--optimize-dnf/--no-optimize-dnf", help="Apply DNF optimizations"),
    image_family: str = typer.Option("rhel-9", "--image-family", help="Image family"),
    image_project: str = typer.Option("rhel-cloud", "--image-project", help="Image project"),
    allow_micro: bool = typer.Option(False, "--allow-micro", help="Override e2-micro block (not recommended)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
):
    """
    Create a GCP instance with sane defaults for notebook development.
    
    Automatically:
    - Blocks e2-micro (too small for DNF/development)
    - Creates swap file on first boot
    - Optimizes DNF configuration (disables debug/source repos)
    """
    # Validate machine type
    if machine_type in BLOCKED_MACHINE_TYPES and not allow_micro:
        console.print(Panel(
            f"[bold red]❌ Machine type '{machine_type}' is blocked[/bold red]\n\n"
            f"This instance type has insufficient resources for development:\n"
            f"• DNF operations will cause OOM or hang\n"
            f"• SSH may become unresponsive\n"
            f"• Container builds will fail\n\n"
            f"[bold green]Recommended alternatives:[/bold green]\n"
            f"• Light testing: [cyan]e2-small[/cyan] (2GB RAM)\n"
            f"• Development: [cyan]e2-medium[/cyan] (4GB RAM)\n"
            f"• Container builds: [cyan]e2-standard-2[/cyan] (8GB RAM)\n\n"
            f"Use [yellow]--allow-micro[/yellow] to override (not recommended).",
            title="Instance Size Error",
            border_style="red",
        ))
        raise typer.Exit(1)

    # Generate startup script
    startup_script = generate_startup_script(swap_gb=swap_gb, optimize_dnf=optimize_dnf)
    
    # Build gcloud command
    gcloud_cmd = [
        "gcloud", "compute", "instances", "create", name,
        f"--zone={zone}",
        f"--machine-type={machine_type}",
        f"--image-family={image_family}",
        f"--image-project={image_project}",
        f"--metadata=startup-script={startup_script}",
    ]
    
    if dry_run:
        console.print(Panel(
            f"[bold]Would execute:[/bold]\n\n[cyan]{' '.join(gcloud_cmd)}[/cyan]\n\n"
            f"[bold]Startup script:[/bold]\n[dim]{startup_script}[/dim]",
            title="Dry Run",
            border_style="yellow",
        ))
        return
    
    # Show what we're doing
    table = Table(title="Instance Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Name", name)
    table.add_row("Zone", zone)
    table.add_row("Machine Type", machine_type)
    table.add_row("Swap Size", f"{swap_gb}GB")
    table.add_row("DNF Optimization", "✓" if optimize_dnf else "✗")
    table.add_row("Image", f"{image_project}/{image_family}")
    console.print(table)
    
    # Execute
    import subprocess
    console.print("\n[bold green]Creating instance...[/bold green]")
    result = subprocess.run(gcloud_cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        console.print(f"\n[bold green]✓ Instance '{name}' created successfully![/bold green]")
        console.print(f"\n[dim]SSH: gcloud compute ssh {name} --zone={zone}[/dim]")
    else:
        console.print(f"\n[bold red]✗ Failed to create instance[/bold red]")
        console.print(f"[red]{result.stderr}[/red]")
        raise typer.Exit(1)


@app.command("bootstrap")
def bootstrap_existing(
    name: str = typer.Argument(..., help="Instance name"),
    zone: str = typer.Option("us-central1-a", "--zone", "-z", help="GCP zone"),
    swap_gb: int = typer.Option(4, "--swap", "-s", help="Swap file size in GB"),
    optimize_dnf: bool = typer.Option(True, "--optimize-dnf/--no-optimize-dnf", help="Apply DNF optimizations"),
):
    """
    Bootstrap an existing GCP instance with swap and DNF optimizations.
    
    Use this for instances that were created without the startup script.
    """
    script = generate_bootstrap_commands(swap_gb=swap_gb, optimize_dnf=optimize_dnf)
    
    console.print(Panel(
        f"[bold]Run this on the instance:[/bold]\n\n"
        f"[cyan]gcloud compute ssh {name} --zone={zone}[/cyan]\n\n"
        f"Then execute:\n[green]{script}[/green]",
        title="Bootstrap Commands",
    ))


@app.command("check")
def check_instance(
    name: str = typer.Argument(..., help="Instance name"),
    zone: str = typer.Option("us-central1-a", "--zone", "-z", help="GCP zone"),
):
    """Check an instance's configuration (swap, DNF, machine type)."""
    import subprocess
    
    # Get instance info
    result = subprocess.run(
        ["gcloud", "compute", "instances", "describe", name, f"--zone={zone}", "--format=json"],
        capture_output=True, text=True,
    )
    
    if result.returncode != 0:
        console.print(f"[red]Failed to get instance info: {result.stderr}[/red]")
        raise typer.Exit(1)
    
    import json
    instance = json.loads(result.stdout)
    machine_type = instance.get("machineType", "").split("/")[-1]
    
    table = Table(title=f"Instance: {name}")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")
    
    # Machine type check
    if machine_type in BLOCKED_MACHINE_TYPES:
        table.add_row("Machine Type", "[red]⚠ Too Small[/red]", f"{machine_type} - consider upgrading")
    else:
        table.add_row("Machine Type", "[green]✓ OK[/green]", machine_type)
    
    console.print(table)
    console.print("\n[dim]For swap/DNF checks, SSH into the instance and run:[/dim]")
    console.print("[cyan]free -h && dnf repolist --enabled | wc -l[/cyan]")


@app.command("tui")
def launch_tui():
    """Launch interactive TUI for provisioning."""
    try:
        from .tui import ProvisionApp
        app = ProvisionApp()
        app.run()
    except ImportError:
        console.print("[yellow]TUI requires textual: pip install textual[/yellow]")
        raise typer.Exit(1)


def generate_startup_script(swap_gb: int = 4, optimize_dnf: bool = True) -> str:
    """Generate a startup script for GCP instances."""
    script_parts = ["#!/bin/bash", "set -euo pipefail", ""]
    
    # Swap setup
    script_parts.extend([
        "# Setup swap",
        "if [[ ! -f /swapfile ]]; then",
        f"    fallocate -l {swap_gb}G /swapfile",
        "    chmod 600 /swapfile",
        "    mkswap /swapfile",
        "    swapon /swapfile",
        "    echo '/swapfile none swap sw 0 0' >> /etc/fstab",
        "    echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf",
        "    sysctl -p /etc/sysctl.d/99-swappiness.conf",
        "fi",
        "",
    ])
    
    # DNF optimization
    if optimize_dnf:
        script_parts.extend([
            "# Optimize DNF",
            "dnf config-manager --disable '*-debug-rpms' '*-source-rpms' 2>/dev/null || true",
            "",
            "if ! grep -q 'max_parallel_downloads' /etc/dnf/dnf.conf; then",
            "    cat >> /etc/dnf/dnf.conf << 'EOF'",
            "",
            "# GCP optimizations",
            "max_parallel_downloads=10",
            "fastestmirror=True",
            "metadata_expire=7d",
            "EOF",
            "fi",
            "",
            "dnf clean all",
            "dnf makecache",
        ])
    
    return "\n".join(script_parts)


def generate_bootstrap_commands(swap_gb: int = 4, optimize_dnf: bool = True) -> str:
    """Generate bootstrap commands for existing instances."""
    return f"""
sudo bash -c '
{generate_startup_script(swap_gb, optimize_dnf)}
'
""".strip()
