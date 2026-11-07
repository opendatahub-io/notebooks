#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Flet (Flutter/Skia) version of GCP provisioning UI.

Run with: uv run --with flet python cli/commands/provision/flet_app.py

This creates a native desktop window using Flutter's Skia renderer.
The same code can also run as a web app with: flet run --web flet_app.py
"""

from __future__ import annotations

import flet as ft
import subprocess
import asyncio


# Machine types with metadata
MACHINE_TYPES = [
    {"value": "e2-small", "label": "e2-small (2GB)", "ram": 2, "ok": True},
    {"value": "e2-medium", "label": "e2-medium (4GB) ✓ Recommended", "ram": 4, "ok": True},
    {"value": "e2-standard-2", "label": "e2-standard-2 (8GB)", "ram": 8, "ok": True},
    {"value": "e2-standard-4", "label": "e2-standard-4 (16GB)", "ram": 16, "ok": True},
    {"value": "n1-standard-4", "label": "n1-standard-4 (15GB) - ML", "ram": 15, "ok": True},
    {"value": "e2-micro", "label": "e2-micro (1GB) ⚠️ BLOCKED", "ram": 1, "ok": False},
]

ZONES = [
    "us-central1-a",
    "us-central1-b", 
    "us-east1-b",
    "us-west1-a",
    "europe-west1-b",
    "asia-east1-a",
]


def main(page: ft.Page):
    """Main Flet application."""
    
    # Page configuration
    page.title = "GCP Instance Provisioning"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.window.width = 900
    page.window.height = 700
    
    # Custom theme with ODH colors
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.BLUE,
        visual_density=ft.VisualDensity.COMFORTABLE,
    )
    
    # State
    log_text = ft.Text("", selectable=True, size=12, font_family="monospace")
    progress = ft.ProgressBar(visible=False, width=400)
    provision_btn = ft.ElevatedButton("🚀 Create Instance", disabled=False)
    warning_text = ft.Text("", color=ft.Colors.ORANGE_400, size=12)
    
    # Form fields
    name_field = ft.TextField(
        label="Instance Name",
        hint_text="my-notebook-instance",
        prefix_icon=ft.Icons.COMPUTER,
        width=350,
    )
    
    zone_dropdown = ft.Dropdown(
        label="Zone",
        width=350,
        options=[ft.dropdown.Option(z) for z in ZONES],
        value="us-central1-a",
    )
    
    machine_dropdown = ft.Dropdown(
        label="Machine Type",
        width=350,
        options=[ft.dropdown.Option(m["value"], m["label"]) for m in MACHINE_TYPES],
        value="e2-medium",
    )
    
    swap_slider = ft.Slider(
        min=1,
        max=8,
        divisions=7,
        value=4,
        label="{value}GB",
        width=300,
    )
    
    swap_label = ft.Text("Swap Size: 4GB", size=14)
    
    dnf_switch = ft.Switch(label="Optimize DNF (disable debug/source repos)", value=True)
    
    def on_swap_change(e):
        swap_label.value = f"Swap Size: {int(swap_slider.value)}GB"
        page.update()
    
    swap_slider.on_change = on_swap_change
    
    def on_machine_change(e):
        selected = next((m for m in MACHINE_TYPES if m["value"] == machine_dropdown.value), None)
        if selected and not selected["ok"]:
            warning_text.value = "⚠️ e2-micro is too small! SSH will hang, DNF will OOM. Choose a larger instance."
            provision_btn.disabled = True
        else:
            warning_text.value = ""
            provision_btn.disabled = False
        page.update()
    
    machine_dropdown.on_change = on_machine_change
    
    def log(msg: str):
        log_text.value += msg + "\n"
        page.update()
    
    def generate_startup_script(swap_gb: int, optimize_dnf: bool) -> str:
        """Generate startup script for the instance."""
        script_parts = ["#!/bin/bash", "set -euo pipefail", ""]
        
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
    
    async def provision_click(e):
        """Handle provision button click."""
        name = name_field.value.strip()
        if not name:
            log("❌ Please enter an instance name")
            return
        
        zone = zone_dropdown.value
        machine = machine_dropdown.value
        swap_gb = int(swap_slider.value)
        optimize_dnf = dnf_switch.value
        
        # Check if blocked machine type
        selected = next((m for m in MACHINE_TYPES if m["value"] == machine), None)
        if selected and not selected["ok"]:
            log("❌ Cannot provision e2-micro - too small for development work")
            return
        
        # Clear log and show progress
        log_text.value = ""
        progress.visible = True
        provision_btn.disabled = True
        page.update()
        
        log("━" * 50)
        log(f"🚀 Creating instance: {name}")
        log(f"   Zone: {zone}")
        log(f"   Machine Type: {machine}")
        log(f"   Swap: {swap_gb}GB")
        log(f"   DNF Optimization: {'✓' if optimize_dnf else '✗'}")
        log("━" * 50)
        log("")
        
        # Generate startup script
        startup_script = generate_startup_script(swap_gb, optimize_dnf)
        log("📝 Generated startup script:")
        for line in startup_script.split("\n")[:8]:
            log(f"   {line}")
        log("   ...")
        log("")
        
        # Build gcloud command
        cmd = [
            "gcloud", "compute", "instances", "create", name,
            f"--zone={zone}",
            f"--machine-type={machine}",
            "--image-family=rhel-9",
            "--image-project=rhel-cloud",
            f"--metadata=startup-script={startup_script}",
        ]
        
        log("⏳ Executing gcloud command...")
        log("")
        
        try:
            # Run in thread to not block UI
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                log("✅ Instance created successfully!")
                log("")
                log(result.stdout)
                log("")
                log("━" * 50)
                log("📋 SSH Command:")
                log(f"   gcloud compute ssh {name} --zone={zone}")
                log("━" * 50)
                
                # Show success snackbar
                page.open(ft.SnackBar(
                    content=ft.Text(f"✓ Instance '{name}' created!"),
                    bgcolor=ft.Colors.GREEN_700,
                ))
            else:
                log("❌ Failed to create instance")
                log(result.stderr)
                
                page.open(ft.SnackBar(
                    content=ft.Text("Failed to create instance"),
                    bgcolor=ft.Colors.RED_700,
                ))
        
        except FileNotFoundError:
            log("❌ gcloud CLI not found. Please install Google Cloud SDK.")
            log("   https://cloud.google.com/sdk/docs/install")
        
        except Exception as ex:
            log(f"❌ Error: {ex}")
        
        finally:
            progress.visible = False
            provision_btn.disabled = False
            page.update()
    
    provision_btn.on_click = provision_click
    
    # Layout
    page.add(
        ft.Row(
            [
                # Left side - Form
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("GCP Instance Provisioning", size=24, weight=ft.FontWeight.BOLD),
                            ft.Text("Create instances with sane defaults for notebook development", 
                                   size=14, color=ft.Colors.GREY_400),
                            ft.Divider(),
                            
                            name_field,
                            zone_dropdown,
                            machine_dropdown,
                            warning_text,
                            
                            ft.Divider(),
                            
                            swap_label,
                            swap_slider,
                            
                            dnf_switch,
                            
                            ft.Divider(),
                            
                            provision_btn,
                            progress,
                        ],
                        spacing=15,
                        width=400,
                    ),
                    padding=20,
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                
                # Right side - Log
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Provisioning Log", size=18, weight=ft.FontWeight.BOLD),
                            ft.Divider(),
                            ft.Container(
                                content=log_text,
                                bgcolor=ft.Colors.BLACK,
                                padding=10,
                                border_radius=5,
                                expand=True,
                            ),
                        ],
                        expand=True,
                    ),
                    padding=20,
                    border_radius=10,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    expand=True,
                ),
            ],
            expand=True,
            spacing=20,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
