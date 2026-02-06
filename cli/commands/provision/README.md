# GCP Provisioning CLI & UI Tools

This directory contains multiple interfaces for provisioning GCP instances with sane defaults for notebook development. All interfaces share the same core logic but offer different user experiences.

## Why This Exists

Developers frequently hit these issues when provisioning GCP instances:

| Problem | Root Cause | Impact |
|---------|------------|--------|
| SSH hangs/unresponsive | e2-micro has 1GB RAM, 0.25 vCPU | Complete lockout, requires serial console |
| DNF operations fail | No swap configured by default | OOM kills, lost work |
| 2-5 minute DNF waits | 550MB+ metadata from 17+ repos | Wasted time on every package operation |

These tools automatically configure instances to avoid these pitfalls.

## Quick Start

```bash
cd /path/to/notebooks/cli/commands/provision

# Choose your preferred interface:

# 1. CLI (for scripts/automation)
uv run --with typer python run_cli.py create my-instance --zone us-central1-a

# 2. TUI (for terminal users, works over SSH)
uv run --with textual python run_tui.py

# 3. Desktop App (native window, GPU-accelerated)
uv run --with flet python flet_app.py

# 4. Web UI (opens browser)
uv run --with nicegui python nicegui_app.py
```

---

## Interface Options

### 1. CLI with Typer (`run_cli.py`)

**Best for:** Shell scripts, automation, CI/CD, power users who prefer command line.

**Features:**
- Shell autocompletion (bash, zsh, fish)
- Rich terminal output with colors and panels
- Machine type validation (blocks e2-micro)
- Dry-run mode for testing

**Installation:**
```bash
# No installation needed, run directly with uv
uv run --with typer python run_cli.py --help
```

**Usage:**
```bash
# See all commands
uv run --with typer python run_cli.py --help

# Create a new instance
uv run --with typer python run_cli.py create my-notebook \
    --zone us-central1-a \
    --machine-type e2-medium \
    --swap 4 \
    --optimize-dnf

# Bootstrap an existing instance (add swap + DNF optimization)
uv run --with typer python run_cli.py bootstrap my-notebook --zone us-central1-a

# Check instance configuration
uv run --with typer python run_cli.py check my-notebook --zone us-central1-a

# Dry run (show what would happen)
uv run --with typer python run_cli.py create my-notebook --dry-run
```

**Shell Completion:**
```bash
# Install completion for zsh
uv run --with typer python run_cli.py --install-completion zsh
source ~/.zshrc

# Now tab-completion works
python run_cli.py create <TAB>
```

**Wrapper Script (for PATH):**
```bash
# Use the provided wrapper
./provision create my-notebook --zone us-central1-a

# Or add to PATH
export PATH="$PATH:$(pwd)"
provision create my-notebook
```

---

### 2. Textual TUI (`run_tui.py`)

**Best for:** Interactive terminal work, SSH sessions, developers who prefer staying in the terminal.

**Features:**
- Full terminal UI with mouse support
- Works over SSH (no X11 required)
- Two-panel layout: form + log output
- Real-time provisioning feedback
- Keyboard navigation

**Screenshot:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🚀 GCP Instance Provisioning                                         15:42 │
├─────────────────────────────────────┬───────────────────────────────────────┤
│ Instance Configuration              │ 📋 Provisioning Log                   │
│ ─────────────────────────────────── │ ───────────────────────────────────── │
│ Instance Name: [my-notebook      ]  │ > Waiting for input...                │
│ Zone:          [us-central1-a    ▼] │                                       │
│ Machine Type:  [e2-medium (4GB)  ▼] │                                       │
│ Swap Size:     [████████░░] 4GB     │                                       │
│ [✓] Optimize DNF                    │                                       │
│                                     │                                       │
│ [ 🚀 Create Instance ]              │                                       │
├─────────────────────────────────────┴───────────────────────────────────────┤
│ esc Quit │ ^p Palette │ Tab Navigate                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Usage:**
```bash
# Launch the TUI
uv run --with textual python run_tui.py
```

**Keyboard Shortcuts:**
| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Navigate between fields |
| `Enter` | Activate button / Select dropdown item |
| `↑` / `↓` | Navigate dropdown options |
| `Esc` | Close dropdown / Quit |
| `^p` | Command palette |

**Requirements:**
- Modern terminal (iTerm2, Ghostty, Kitty, WezTerm, etc.)
- Works in tmux/screen
- Works over SSH

---

### 3. Trogon Auto-TUI (`run_trogon.py`)

**Best for:** Exploring CLI options visually, users unfamiliar with the CLI flags.

**What it does:** Automatically generates a TUI from the CLI commands. No extra code needed - it introspects the Typer app and builds a form UI.

**Usage:**
```bash
# Launch auto-generated TUI
uv run --with typer --with trogon python run_trogon.py tui

# Or use as regular CLI
uv run --with typer --with trogon python run_trogon.py create my-notebook
uv run --with typer --with trogon python run_trogon.py --help
```

**Keyboard Shortcuts:**
| Key | Action |
|-----|--------|
| `^t` | Focus command tree (left panel) |
| `↑` / `↓` | Navigate commands |
| `→` | Expand command to see options |
| `Enter` | Select command (shows form) |
| `^r` | Close TUI & run the command |
| `^s` | Search commands |
| `q` | Quit |

**How to use:**
1. Press `^t` to focus the command tree
2. Use arrow keys to navigate to a command (e.g., `create`)
3. Press `Enter` to select it
4. Fill in the form fields on the right
5. Press `^r` to execute

**Known Issue:** Don't press `^o` (Command Info) before selecting a command - it crashes (Trogon bug).

---

### 4. Flet Desktop App (`flet_app.py`)

**Best for:** Users who prefer native GUI applications, visual demonstrations.

**Features:**
- Native macOS/Linux window
- Flutter/Skia GPU-accelerated rendering (60fps)
- Material Design 3 dark theme
- Smooth animations and transitions
- Same code can run as web app

**Screenshot:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ● ● ●                    GCP Instance Provisioning                          │
├─────────────────────────────────────┬───────────────────────────────────────┤
│  ╭─────────────────────────────╮    │  ╭─────────────────────────────────╮  │
│  │ 📦 Instance Name            │    │  │ 📋 Provisioning Log             │  │
│  │ [my-notebook            ]   │    │  │                                 │  │
│  │                             │    │  │ > Ready                         │  │
│  │ 🌍 Zone                     │    │  │                                 │  │
│  │ [us-central1-a          ▼]  │    │  │                                 │  │
│  │                             │    │  │                                 │  │
│  │ 💻 Machine Type             │    │  │                                 │  │
│  │ [e2-medium (4GB) ✓      ▼]  │    │  │                                 │  │
│  │                             │    │  │                                 │  │
│  │ 💾 Swap Size: 4GB           │    │  │                                 │  │
│  │ [━━━━━━━━━━━━━━━░░░░░░░░]   │    │  │                                 │  │
│  │                             │    │  │                                 │  │
│  │ ⚡ Optimize DNF  [━━●]      │    │  │                                 │  │
│  │                             │    │  │                                 │  │
│  │ [ 🚀 Create Instance    ]   │    │  │                                 │  │
│  ╰─────────────────────────────╯    │  ╰─────────────────────────────────╯  │
└─────────────────────────────────────┴───────────────────────────────────────┘
```

**Usage:**
```bash
# Launch desktop app
uv run --with flet python flet_app.py

# Run as web app instead (opens browser)
uv run --with flet flet run --web flet_app.py
```

**Notes:**
- First run downloads Flutter runtime (~100MB, cached)
- Requires display (won't work over SSH without X11 forwarding)
- GPU acceleration requires OpenGL support

---

### 5. NiceGUI Web UI (`nicegui_app.py`)

**Best for:** Browser-based access, remote machines with port forwarding, sharing UI with non-technical users.

**Features:**
- Modern web interface (Quasar/Vue.js)
- Dark theme
- Real-time log streaming via WebSocket
- Works with port forwarding for remote access
- No installation on client side

**Screenshot:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🚀 GCP Instance Provisioning                              notebooks-cli    │
├─────────────────────────────────────┬───────────────────────────────────────┤
│  Instance Configuration             │  Provisioning Log                     │
│  ───────────────────────────────    │  ─────────────────────────────────    │
│  Instance Name                      │  ┌─────────────────────────────────┐  │
│  [                              ]   │  │ $ Ready for provisioning...     │  │
│                                     │  │                                 │  │
│  Zone                               │  │                                 │  │
│  [us-central1-a                 ▼]  │  │                                 │  │
│                                     │  │                                 │  │
│  Machine Type                       │  │                                 │  │
│  [e2-medium (4GB) ✓ Recommended ▼]  │  │                                 │  │
│                                     │  │                                 │  │
│  Swap Size                          │  │                                 │  │
│  1GB [━━━━━━━━━━●━━━━━━━━━] 16GB   │  │                                 │  │
│        4GB                          │  │                                 │  │
│                                     │  │                                 │  │
│  [✓] Optimize DNF repositories      │  └─────────────────────────────────┘  │
│                                     │                                       │
│  [ 🚀 CREATE INSTANCE ]             │                                       │
└─────────────────────────────────────┴───────────────────────────────────────┘
```

**Usage:**
```bash
# Start web server (opens browser automatically)
uv run --with nicegui python nicegui_app.py

# Server runs at http://localhost:8080
```

**Remote Access (via SSH port forwarding):**
```bash
# On your local machine
ssh -L 8080:localhost:8080 user@remote-host

# On remote host
cd /path/to/notebooks/cli/commands/provision
uv run --with nicegui python nicegui_app.py

# Open http://localhost:8080 in your local browser
```

---

## Comparison Table

| Feature | CLI | Textual TUI | Trogon | Flet Desktop | NiceGUI Web |
|---------|-----|-------------|--------|--------------|-------------|
| **File** | `run_cli.py` | `run_tui.py` | `run_trogon.py` | `flet_app.py` | `nicegui_app.py` |
| **Works over SSH** | ✓ | ✓ | ✓ | ✗ | ✓ (port forward) |
| **Mouse support** | ✗ | ✓ | ✓ | ✓ | ✓ |
| **Shell completion** | ✓ | ✗ | ✓ | ✗ | ✗ |
| **Visual forms** | ✗ | ✓ | ✓ | ✓ | ✓ |
| **Real-time logs** | ✓ | ✓ | ✗ | ✓ | ✓ |
| **Scriptable** | ✓ | ✗ | ✓ | ✗ | ✗ |
| **Dependencies** | typer | textual | typer, trogon | flet | nicegui |
| **First run speed** | Fast | Fast | Fast | Slow (downloads Flutter) | Medium |

---

## File Structure

```
cli/commands/provision/
├── README.md           # This file
├── __init__.py         # Module init
├── command.py          # Core CLI logic (Typer commands, validation)
├── run_cli.py          # CLI entry point with completion support
├── provision           # Bash wrapper for PATH integration
├── tui.py              # Textual TUI implementation
├── run_tui.py          # TUI entry point
├── run_trogon.py       # Trogon auto-TUI + CLI
├── flet_app.py         # Flet desktop application
└── nicegui_app.py      # NiceGUI web application
```

---

## Configuration Defaults

All interfaces apply these sane defaults:

| Setting | Default | Why |
|---------|---------|-----|
| Machine Type | `e2-medium` | 4GB RAM, sufficient for DNF + development |
| Blocked Types | `e2-micro`, `f1-micro`, `g1-small` | Too small, causes OOM/hangs |
| Swap Size | 4GB | Prevents OOM during DNF operations |
| DNF Optimization | Enabled | Disables debug/source repos, saves 300MB+ |

---

## Dependencies

Install dependencies on-demand with `uv run --with`:

```bash
# CLI only
uv run --with typer python run_cli.py --help

# TUI
uv run --with textual python run_tui.py

# Trogon (auto-TUI)
uv run --with typer --with trogon python run_trogon.py tui

# Flet (desktop)
uv run --with flet python flet_app.py

# NiceGUI (web)
uv run --with nicegui python nicegui_app.py
```

Or install all at once:
```bash
uv pip install typer rich textual trogon flet nicegui
```

---

## Troubleshooting

### CLI: Shell completion not working
```bash
# Make sure you installed for the right shell
uv run --with typer python run_cli.py --install-completion zsh
source ~/.zshrc

# Completion only works when running the script directly, not via `uv run`
./provision create <TAB>  # Works
uv run ... python run_cli.py create <TAB>  # Doesn't work
```

### TUI: Rendering issues
```bash
# Try forcing a simpler terminal mode
TERM=xterm-256color uv run --with textual python run_tui.py

# Or use textual's dev mode for debugging
uv run --with textual textual run --dev run_tui.py
```

### Flet: Slow first startup
First run downloads the Flutter runtime (~100MB). Subsequent runs are fast.

### NiceGUI: Port already in use
```bash
# Kill existing process
lsof -ti:8080 | xargs kill -9

# Or use a different port
# Edit nicegui_app.py: ui.run(port=8081)
```

### Trogon: Crash on ^o
Known bug - don't press `^o` before selecting a command. Use `^t` to focus tree first.

---

## Contributing

When adding new provisioning options:

1. Add the core logic to `command.py`
2. Update the TUI in `tui.py` to include new form fields
3. Update `flet_app.py` and `nicegui_app.py` to match
4. Update this README with new options

---

## See Also

- [GCP Provisioning First Steps Guide](../../../docs/gcpprovisioningfirststeps.md) - Manual setup instructions
- [CLI Provisioning Design Document](../../../docs/cli-provisioning-design.md) - Technical architecture
