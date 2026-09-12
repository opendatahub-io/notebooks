#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
NiceGUI (Web UI) version of GCP provisioning.

Run with: uv run --with nicegui python cli/commands/provision/nicegui_app.py

Opens a browser tab at http://localhost:8080 with the provisioning UI.
"""

from __future__ import annotations

from nicegui import ui, app
import subprocess
import asyncio


# Machine types
MACHINE_TYPES = {
    "e2-small": {"label": "e2-small (2GB) - Light testing", "ram": 2, "blocked": False},
    "e2-medium": {"label": "e2-medium (4GB) ✓ Recommended", "ram": 4, "blocked": False},
    "e2-standard-2": {"label": "e2-standard-2 (8GB) - Container builds", "ram": 8, "blocked": False},
    "e2-standard-4": {"label": "e2-standard-4 (16GB) - Heavy workloads", "ram": 16, "blocked": False},
    "n1-standard-4": {"label": "n1-standard-4 (15GB) - ML workloads", "ram": 15, "blocked": False},
    "e2-micro": {"label": "e2-micro (1GB) ⚠️ BLOCKED", "ram": 1, "blocked": True},
}

ZONES = [
    "us-central1-a",
    "us-central1-b",
    "us-east1-b",
    "us-west1-a",
    "europe-west1-b",
]


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


@ui.page('/')
def main_page():
    """Main provisioning page."""
    
    # Dark theme
    ui.dark_mode().enable()
    
    # Header
    with ui.header().classes('items-center justify-between'):
        ui.label('🚀 GCP Instance Provisioning').classes('text-xl font-bold')
        ui.label('notebooks-cli').classes('text-sm opacity-70')
    
    # Main content
    with ui.row().classes('w-full gap-4 p-4'):
        
        # Left panel - Form
        with ui.card().classes('w-96'):
            ui.label('Instance Configuration').classes('text-lg font-bold mb-4')
            
            name_input = ui.input(
                label='Instance Name',
                placeholder='my-notebook-instance',
            ).classes('w-full')
            
            zone_select = ui.select(
                ZONES,
                label='Zone',
                value='us-central1-a',
            ).classes('w-full')
            
            machine_select = ui.select(
                {k: v["label"] for k, v in MACHINE_TYPES.items()},
                label='Machine Type',
                value='e2-medium',
            ).classes('w-full')
            
            warning_label = ui.label('').classes('text-orange-400 text-sm')
            
            def on_machine_change():
                if MACHINE_TYPES.get(machine_select.value, {}).get("blocked"):
                    warning_label.text = "⚠️ e2-micro is too small! SSH will hang, DNF will OOM."
                else:
                    warning_label.text = ""
            
            machine_select.on_value_change(on_machine_change)
            
            ui.separator()
            
            swap_label = ui.label('Swap Size: 4GB')
            swap_slider = ui.slider(min=1, max=8, value=4, step=1).classes('w-full')
            swap_slider.on_value_change(lambda: swap_label.set_text(f'Swap Size: {int(swap_slider.value)}GB'))
            
            dnf_checkbox = ui.checkbox('Optimize DNF (disable debug/source repos)', value=True)
            
            ui.separator()
            
            provision_btn = ui.button('🚀 Create Instance', color='green').classes('w-full')
            spinner = ui.spinner('dots', size='lg').classes('hidden')
        
        # Right panel - Log
        with ui.card().classes('flex-grow'):
            ui.label('Provisioning Log').classes('text-lg font-bold mb-4')
            
            log_area = ui.log(max_lines=100).classes('w-full h-96 bg-black font-mono text-sm')
    
    async def provision():
        """Run provisioning."""
        name = name_input.value.strip()
        if not name:
            ui.notify('Please enter an instance name', type='warning')
            return
        
        machine = machine_select.value
        if MACHINE_TYPES.get(machine, {}).get("blocked"):
            ui.notify('Cannot provision e2-micro - too small', type='negative')
            return
        
        zone = zone_select.value
        swap_gb = int(swap_slider.value)
        optimize_dnf = dnf_checkbox.value
        
        # Show spinner
        spinner.classes(remove='hidden')
        provision_btn.disable()
        
        log_area.clear()
        log_area.push("━" * 50)
        log_area.push(f"🚀 Creating instance: {name}")
        log_area.push(f"   Zone: {zone}")
        log_area.push(f"   Machine Type: {machine}")
        log_area.push(f"   Swap: {swap_gb}GB")
        log_area.push(f"   DNF Optimization: {'✓' if optimize_dnf else '✗'}")
        log_area.push("━" * 50)
        log_area.push("")
        
        startup_script = generate_startup_script(swap_gb, optimize_dnf)
        log_area.push("📝 Generated startup script (first 8 lines):")
        for line in startup_script.split("\n")[:8]:
            log_area.push(f"   {line}")
        log_area.push("   ...")
        log_area.push("")
        
        cmd = [
            "gcloud", "compute", "instances", "create", name,
            f"--zone={zone}",
            f"--machine-type={machine}",
            "--image-family=rhel-9",
            "--image-project=rhel-cloud",
            f"--metadata=startup-script={startup_script}",
        ]
        
        log_area.push("⏳ Executing gcloud command...")
        log_area.push("")
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                log_area.push("✅ Instance created successfully!")
                log_area.push("")
                for line in result.stdout.split("\n"):
                    log_area.push(line)
                log_area.push("")
                log_area.push("━" * 50)
                log_area.push("📋 SSH Command:")
                log_area.push(f"   gcloud compute ssh {name} --zone={zone}")
                log_area.push("━" * 50)
                
                ui.notify(f"Instance '{name}' created!", type='positive')
            else:
                log_area.push("❌ Failed to create instance")
                log_area.push(result.stderr)
                ui.notify("Failed to create instance", type='negative')
        
        except FileNotFoundError:
            log_area.push("❌ gcloud CLI not found")
            ui.notify("gcloud CLI not found", type='negative')
        
        except Exception as e:
            log_area.push(f"❌ Error: {e}")
            ui.notify(str(e), type='negative')
        
        finally:
            spinner.classes(add='hidden')
            provision_btn.enable()
    
    provision_btn.on_click(provision)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="GCP Provisioning",
        port=8080,
        dark=True,
        reload=False,
    )
