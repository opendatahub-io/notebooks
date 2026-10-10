# SPDX-License-Identifier: Apache-2.0
"""Textual TUI for GCP provisioning."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    Select,
    Switch,
    Label,
    ProgressBar,
    Log,
    Rule,
)
from textual.binding import Binding
from textual import work
from textual.worker import Worker, get_current_worker

import subprocess
import asyncio
from typing import Optional


# Machine type options with descriptions
MACHINE_TYPES = [
    ("e2-small (2GB) - Light testing", "e2-small"),
    ("e2-medium (4GB) - Development ✓", "e2-medium"),
    ("e2-standard-2 (8GB) - Container builds", "e2-standard-2"),
    ("e2-standard-4 (16GB) - Heavy workloads", "e2-standard-4"),
    ("n1-standard-4 (15GB) - ML workloads", "n1-standard-4"),
    ("─────────────────────────", ""),
    ("e2-micro (1GB) ⚠️ NOT RECOMMENDED", "e2-micro"),
]

ZONES = [
    ("us-central1-a", "us-central1-a"),
    ("us-central1-b", "us-central1-b"),
    ("us-east1-b", "us-east1-b"),
    ("us-west1-a", "us-west1-a"),
    ("europe-west1-b", "europe-west1-b"),
]

SWAP_SIZES = [
    ("2 GB", 2),
    ("4 GB (recommended)", 4),
    ("8 GB", 8),
]


class ProvisionApp(App):
    """A Textual app for GCP instance provisioning."""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
    }
    
    #form-container {
        padding: 1 2;
        border: solid green;
        height: 100%;
    }
    
    #log-container {
        padding: 1 2;
        border: solid cyan;
        height: 100%;
    }
    
    .form-row {
        height: auto;
        margin-bottom: 1;
    }
    
    .form-label {
        width: 20;
        text-style: bold;
    }
    
    Input {
        width: 100%;
    }
    
    Select {
        width: 100%;
    }
    
    #provision-btn {
        margin-top: 2;
        width: 100%;
    }
    
    #provision-btn.success {
        background: green;
    }
    
    .warning {
        color: yellow;
        text-style: italic;
    }
    
    .error {
        color: red;
        text-style: bold;
    }
    
    #status {
        height: 3;
        content-align: center middle;
        margin-top: 1;
    }
    
    Log {
        height: 1fr;
    }
    
    ProgressBar {
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("enter", "provision", "Provision", show=False),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="form-container"):
            yield Static("🚀 GCP Instance Provisioning", classes="title")
            yield Rule()
            
            # Instance name
            with Horizontal(classes="form-row"):
                yield Label("Instance Name:", classes="form-label")
                yield Input(placeholder="my-notebook-instance", id="name")
            
            # Zone
            with Horizontal(classes="form-row"):
                yield Label("Zone:", classes="form-label")
                yield Select(ZONES, value="us-central1-a", id="zone")
            
            # Machine type
            with Horizontal(classes="form-row"):
                yield Label("Machine Type:", classes="form-label")
                yield Select(MACHINE_TYPES, value="e2-medium", id="machine-type")
            
            yield Static("", id="machine-warning", classes="warning")
            
            # Swap size
            with Horizontal(classes="form-row"):
                yield Label("Swap Size:", classes="form-label")
                yield Select(SWAP_SIZES, value=4, id="swap-size")
            
            # DNF optimization toggle
            with Horizontal(classes="form-row"):
                yield Label("Optimize DNF:", classes="form-label")
                yield Switch(value=True, id="optimize-dnf")
                yield Static("Disable debug/source repos, faster metadata", classes="form-hint")
            
            yield Rule()
            yield Button("🚀 Create Instance", id="provision-btn", variant="success")
            yield Static("", id="status")
            yield ProgressBar(id="progress", show_eta=False)
        
        with Container(id="log-container"):
            yield Static("📋 Provisioning Log", classes="title")
            yield Rule()
            yield Log(id="log", highlight=True)
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Focus the name input on mount."""
        self.query_one("#name", Input).focus()
        self.query_one("#progress", ProgressBar).update(total=100, progress=0)
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle machine type selection changes."""
        if event.select.id == "machine-type":
            warning = self.query_one("#machine-warning", Static)
            if event.value == "e2-micro":
                warning.update("⚠️  e2-micro is too small! SSH will hang, DNF will OOM.")
            elif event.value == "":
                # Separator selected, reset to default
                event.select.value = "e2-medium"
                warning.update("")
            else:
                warning.update("")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "provision-btn":
            self.action_provision()
    
    def action_provision(self) -> None:
        """Start the provisioning process."""
        name = self.query_one("#name", Input).value.strip()
        if not name:
            self.query_one("#status", Static).update("[red]Please enter an instance name[/red]")
            return
        
        machine_type = self.query_one("#machine-type", Select).value
        if machine_type == "e2-micro":
            self.query_one("#status", Static).update(
                "[red]e2-micro blocked. Use --allow-micro in CLI to override.[/red]"
            )
            return
        
        zone = self.query_one("#zone", Select).value
        swap_gb = self.query_one("#swap-size", Select).value
        optimize_dnf = self.query_one("#optimize-dnf", Switch).value
        
        # Start provisioning in background
        self.provision_instance(name, zone, machine_type, swap_gb, optimize_dnf)
    
    @work(exclusive=True, thread=True)
    def provision_instance(
        self,
        name: str,
        zone: str,
        machine_type: str,
        swap_gb: int,
        optimize_dnf: bool,
    ) -> None:
        """Run the provisioning in a background thread."""
        worker = get_current_worker()
        log = self.query_one("#log", Log)
        progress = self.query_one("#progress", ProgressBar)
        status = self.query_one("#status", Static)
        button = self.query_one("#provision-btn", Button)
        
        # Disable button during provisioning
        self.call_from_thread(button.set_class, True, "disabled")
        self.call_from_thread(status.update, "[yellow]Provisioning...[/yellow]")
        
        def log_write(msg: str) -> None:
            self.call_from_thread(log.write_line, msg)
        
        def set_progress(value: int) -> None:
            self.call_from_thread(progress.update, progress=value)
        
        try:
            log_write(f"[bold]Creating instance:[/bold] {name}")
            log_write(f"  Zone: {zone}")
            log_write(f"  Machine: {machine_type}")
            log_write(f"  Swap: {swap_gb}GB")
            log_write(f"  DNF optimization: {optimize_dnf}")
            log_write("")
            set_progress(10)
            
            # Generate startup script
            from .command import generate_startup_script
            startup_script = generate_startup_script(swap_gb=swap_gb, optimize_dnf=optimize_dnf)
            
            log_write("[cyan]Generated startup script:[/cyan]")
            for line in startup_script.split("\n")[:10]:
                log_write(f"  [dim]{line}[/dim]")
            log_write("  [dim]...[/dim]")
            log_write("")
            set_progress(20)
            
            # Build gcloud command
            cmd = [
                "gcloud", "compute", "instances", "create", name,
                f"--zone={zone}",
                f"--machine-type={machine_type}",
                "--image-family=rhel-9",
                "--image-project=rhel-cloud",
                f"--metadata=startup-script={startup_script}",
            ]
            
            log_write("[yellow]Executing gcloud command...[/yellow]")
            set_progress(30)
            
            # Run command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            
            set_progress(90)
            
            if result.returncode == 0:
                log_write("")
                log_write("[bold green]✓ Instance created successfully![/bold green]")
                log_write("")
                log_write(result.stdout)
                log_write("")
                log_write(f"[bold]SSH command:[/bold]")
                log_write(f"  [cyan]gcloud compute ssh {name} --zone={zone}[/cyan]")
                self.call_from_thread(status.update, "[green]✓ Instance created![/green]")
            else:
                log_write("")
                log_write("[bold red]✗ Failed to create instance[/bold red]")
                log_write(f"[red]{result.stderr}[/red]")
                self.call_from_thread(status.update, "[red]✗ Failed[/red]")
            
            set_progress(100)
            
        except Exception as e:
            log_write(f"[red]Error: {e}[/red]")
            self.call_from_thread(status.update, f"[red]Error: {e}[/red]")
        
        finally:
            self.call_from_thread(button.set_class, False, "disabled")


def main():
    """Entry point for the TUI."""
    app = ProvisionApp()
    app.run()


if __name__ == "__main__":
    main()
