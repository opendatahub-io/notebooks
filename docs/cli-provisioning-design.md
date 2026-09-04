# CLI Provisioning Enhancement Design

This document outlines the design for enhancing the `notebooks-cli` with GCP provisioning capabilities, addressing common developer pain points.

## Problem Statement

Developers frequently encounter these issues when provisioning GCP instances for notebook development:

| Pain Point | Root Cause | Impact |
|------------|------------|--------|
| SSH hangs/unresponsive | e2-micro has 1GB RAM, 0.25 vCPU | Complete lockout, requires serial console |
| DNF operations fail/hang | No swap configured by default | OOM kills, lost work |
| 2-5 minute DNF waits | 550MB+ metadata from 17+ repos | Wasted time on every package operation |
| Repeated manual setup | No automation for post-provision config | Error-prone, forgotten steps |

## Solution Architecture

### Layered UI Approach

```
┌─────────────────────────────────────────────────────────────────┐
│                     notebooks-cli provision                      │
├─────────────────────────────────────────────────────────────────┤
│                        Core Logic (Python)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Instance     │  │ Swap         │  │ DNF                    │ │
│  │ Validation   │  │ Configuration│  │ Optimization           │ │
│  │ (block micro)│  │ (4GB default)│  │ (disable debug/source) │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
├────────────┬────────────┬────────────┬──────────────────────────┤
│    CLI     │    TUI     │   Web UI   │     Desktop App          │
│  (Typer)   │ (Textual)  │ (NiceGUI)  │     (Flet)               │
│            │            │            │                          │
│  Scripting │ Interactive│ Point-and- │  Native GUI              │
│  CI/CD     │ SSH-safe   │ Click      │  Cross-platform          │
└────────────┴────────────┴────────────┴──────────────────────────┘
```

### Command Structure

```bash
notebooks provision create <name>     # Create instance with sane defaults
notebooks provision bootstrap <name>  # Fix existing instance
notebooks provision check <name>      # Verify instance configuration
notebooks provision tui               # Launch interactive TUI
notebooks provision ui                # Launch web UI (future)
```

## Implementation Phases

### Phase 1: CLI Foundation (Current)

**Files created:**
- `cli/commands/provision/__init__.py`
- `cli/commands/provision/command.py`
- `cli/commands/provision/tui.py`

**Features:**
- Instance creation with startup script
- Machine type validation (blocks e2-micro by default)
- Automatic swap configuration
- DNF optimization (disables debug/source repos)
- Dry-run mode

**Dependencies to add to pyproject.toml:**
```toml
[dependency-groups]
cli = [
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
]

tui = [
    "textual>=0.50.0",
]

webui = [
    "nicegui>=1.4.0",
]

desktop = [
    "flet>=0.21.0",
]
```

### Phase 2: Enhanced TUI (Next)

The Textual-based TUI provides:
- Interactive form for all provisioning options
- Real-time log output
- Progress indicators
- Mouse and keyboard navigation
- Works over SSH

**Screenshot mockup:**
```
┌─ GCP Instance Provisioning ─────────────────┬─ Provisioning Log ──────────────┐
│                                             │                                  │
│  Instance Name: [my-notebook-instance    ]  │  Creating instance: my-notebook  │
│                                             │    Zone: us-central1-a           │
│  Zone:          [us-central1-a          ▼]  │    Machine: e2-medium            │
│                                             │    Swap: 4GB                     │
│  Machine Type:  [e2-medium (4GB) ✓      ▼]  │                                  │
│                                             │  Executing gcloud command...     │
│  Swap Size:     [4 GB (recommended)     ▼]  │                                  │
│                                             │  ✓ Instance created!             │
│  Optimize DNF:  [✓]  Disable debug/source   │                                  │
│                                             │  SSH: gcloud compute ssh         │
│  ─────────────────────────────────────────  │       my-notebook --zone=...     │
│  [ 🚀 Create Instance                    ]  │                                  │
│                                             │                                  │
│  Status: ✓ Instance created!                │                                  │
│  ████████████████████████████████████ 100%  │                                  │
└─────────────────────────────────────────────┴──────────────────────────────────┘
```

### Phase 3: Web UI (Future)

Using NiceGUI for a browser-based experience:

```python
# notebooks provision ui
from nicegui import ui

@ui.page('/')
def main():
    with ui.card().classes('w-96'):
        ui.label('GCP Provisioning').classes('text-h5')
        name = ui.input('Instance Name')
        zone = ui.select(['us-central1-a', ...], label='Zone')
        machine = ui.select(['e2-small', 'e2-medium', ...], label='Machine Type')
        swap = ui.slider(min=1, max=8, value=4)
        ui.button('Create', on_click=lambda: provision(name.value, ...))

ui.run(title='GCP Provisioning', port=8080)
```

### Phase 4: Desktop App (Future)

Using Flet for native desktop experience:

```python
# notebooks provision desktop
import flet as ft

def main(page: ft.Page):
    page.title = "GCP Provisioning"
    # Flutter-based UI with Skia renderer
    # Same codebase works as web app too
    
ft.app(target=main)
```

## Startup Script Generation

The core logic generates a startup script that runs on first boot:

```bash
#!/bin/bash
set -euo pipefail

# Setup swap (before any DNF operations)
if [[ ! -f /swapfile ]]; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
    sysctl -p /etc/sysctl.d/99-swappiness.conf
fi

# Optimize DNF
dnf config-manager --disable '*-debug-rpms' '*-source-rpms' 2>/dev/null || true

if ! grep -q 'max_parallel_downloads' /etc/dnf/dnf.conf; then
    cat >> /etc/dnf/dnf.conf << 'EOF'

# GCP optimizations
max_parallel_downloads=10
fastestmirror=True
metadata_expire=7d
EOF
fi

dnf clean all
dnf makecache
```

## Machine Type Validation

The CLI blocks these machine types by default:

| Blocked | RAM | Reason |
|---------|-----|--------|
| e2-micro | 1GB | SSH hangs, DNF OOMs |
| f1-micro | 0.6GB | Too small for anything |
| g1-small | 1.7GB | Marginal, still risky |

Recommended alternatives:

| Use Case | Machine Type | RAM |
|----------|--------------|-----|
| Light testing | e2-small | 2GB |
| Development | e2-medium | 4GB |
| Container builds | e2-standard-2 | 8GB |
| ML workloads | n1-standard-4 | 15GB |

## Integration with Existing CLI

The provisioning commands integrate with the existing `notebooks-cli` structure:

```
cli/
├── commands/
│   ├── aipcc.py
│   ├── konflux.py
│   ├── manifest.py
│   ├── provision/          # NEW
│   │   ├── __init__.py
│   │   ├── command.py      # CLI commands
│   │   ├── tui.py          # Textual TUI
│   │   ├── webui.py        # NiceGUI (future)
│   │   └── desktop.py      # Flet (future)
│   ├── quay.py
│   └── security.py
├── main.py
└── ...
```

## Testing Strategy

1. **Unit tests**: Test startup script generation, validation logic
2. **Integration tests**: Test gcloud command generation (with mocks)
3. **Manual tests**: Test on actual GCP instances
4. **TUI tests**: Use Textual's built-in testing framework

## Future Enhancements

1. **Templates**: Pre-configured instance profiles (ml-dev, container-builder, etc.)
2. **Cost estimates**: Show estimated hourly/monthly cost before provisioning
3. **GPU support**: Add CUDA/ROCm instance types with appropriate setup
4. **Multi-cloud**: Extend to AWS/Azure provisioning
5. **State management**: Track provisioned instances, auto-cleanup

## References

- [GCP First Steps Guide](./gcpprovisioningfirststeps.md)
- [Textual Documentation](https://textual.textualize.io/)
- [NiceGUI Documentation](https://nicegui.io/)
- [Flet Documentation](https://flet.dev/)
- [notebooks-cli branch](https://github.com/opendatahub-io/notebooks/tree/notebooks-cli)

---

*Last updated: January 2026*
