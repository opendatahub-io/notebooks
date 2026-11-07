# 5. Multi-Interface CLI for GCP Provisioning

Date: 2026-01-17

## Status

Proposed

## Context

Developers provisioning GCP instances for notebook development frequently encounter these problems:

| Problem | Root Cause | Impact |
|---------|------------|--------|
| SSH hangs/unresponsive | e2-micro has 1GB RAM, 0.25 vCPU | Complete lockout, requires serial console |
| DNF operations fail/OOM | No swap configured by default | Lost work, crashed builds |
| 2-5 minute DNF waits | 550MB+ metadata from 17+ RHEL repos | Wasted time on every package operation |
| Forgotten setup steps | Manual post-provision configuration | Error-prone, inconsistent environments |

These issues affect both new team members and experienced developers who forget the optimal configuration steps.

We need a tool that:

1. Prevents common mistakes (e.g., blocking undersized machine types)
2. Automates best-practice configuration (swap, DNF optimization)
3. Works in various contexts (scripts, SSH sessions, local development)
4. Is discoverable and self-documenting

## Decision

We will implement a **multi-interface provisioning tool** with the same core logic exposed through five different user interfaces:

### Interface Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interfaces                          │
├─────────────┬─────────────┬─────────────┬───────────┬───────────┤
│  Typer CLI  │ Textual TUI │   Trogon    │   Flet    │  NiceGUI  │
│  (scripts)  │   (SSH)     │ (auto-TUI)  │ (desktop) │   (web)   │
├─────────────┴─────────────┴─────────────┴───────────┴───────────┤
│                     Core Logic (command.py)                      │
│  • Machine type validation    • Startup script generation       │
│  • Blocked types list         • gcloud command construction      │
└─────────────────────────────────────────────────────────────────┘
```

### Framework Choices

| Interface | Framework | Why This Choice |
|-----------|-----------|-----------------|
| **CLI** | Typer + Rich | Modern, type-hint-based, shell completion, beautiful output |
| **TUI** | Textual | Works over SSH, 60fps rendering, CSS-like styling, async-first |
| **Auto-TUI** | Trogon | Zero-effort TUI from existing CLI, good for discoverability |
| **Desktop** | Flet | Flutter/Skia renderer, native window, same code runs as web |
| **Web** | NiceGUI | Browser-based, Quasar/Vue components, works with port forwarding |

### Why Multiple Interfaces?

Different contexts require different UIs:

| Context | Best Interface | Why |
|---------|---------------|-----|
| CI/CD pipelines | CLI | Scriptable, non-interactive |
| SSH to remote machine | TUI | Works in terminal, no port forwarding |
| Exploring options | Trogon | Visual form, shows all flags |
| Local development | Flet/NiceGUI | Point-and-click convenience |
| Sharing with non-devs | NiceGUI | Browser-based, familiar |

### Why Not Just One Interface?

- **CLI alone**: Not discoverable, requires memorizing flags
- **TUI alone**: Not scriptable, can't use in CI
- **Web alone**: Requires port forwarding for remote access
- **Desktop alone**: Doesn't work over SSH

By sharing core logic, we maintain consistency while optimizing for each context.

### Technology Evaluation

We considered and rejected:

| Alternative | Reason for Rejection |
|-------------|---------------------|
| **Streamlit** | Too opinionated, not ideal for action-oriented UIs |
| **Gradio** | Focused on ML demos, not provisioning workflows |
| **Click** | Typer is built on Click but more Pythonic |
| **curses** | Too low-level, Textual is a better abstraction |
| **PyQt/Tkinter** | Heavy, not modern-looking, complex |
| **UnoCSS** | Requires Node.js build step; Tailwind already in NiceGUI |

### Styling Considerations

| Framework | Styling Approach |
|-----------|------------------|
| Textual | TCSS (Textual CSS), similar to CSS but for terminals |
| Flet | Material Design 3, built-in theming |
| NiceGUI | Tailwind CSS via Quasar (already included) |

We decided against adding UnoCSS to NiceGUI because:
- Tailwind is already available and working
- UnoCSS would require Node.js tooling (build step)
- Marginal benefit (~6KB vs ~30KB) doesn't justify complexity

## Implementation

### File Structure

```
cli/commands/provision/
├── __init__.py           # Module init
├── command.py            # Core logic: validation, script generation
├── run_cli.py            # CLI entry point
├── provision             # Bash wrapper for PATH integration
├── tui.py                # Textual TUI implementation
├── run_tui.py            # TUI entry point
├── run_trogon.py         # Trogon auto-TUI + CLI
├── flet_app.py           # Flet desktop application
├── nicegui_app.py        # NiceGUI web application
├── README.md             # Main documentation
├── README-typer.md       # Typer coding guide
├── README-textual.md     # Textual coding guide
├── README-trogon.md      # Trogon coding guide
├── README-flet.md        # Flet coding guide
└── README-nicegui.md     # NiceGUI coding guide
```

### Core Safety Features

All interfaces enforce:

1. **Machine type blocking**: `e2-micro`, `f1-micro`, `g1-small` are rejected
2. **Swap configuration**: 1-16GB, default 4GB
3. **DNF optimization**: Disable debug/source repos by default
4. **Startup script generation**: Consistent configuration across instances

### Dependency Management

Dependencies are installed on-demand via `uv run --with`:

```bash
uv run --with typer python run_cli.py           # CLI
uv run --with textual python run_tui.py         # TUI
uv run --with typer --with trogon python run_trogon.py tui  # Auto-TUI
uv run --with flet python flet_app.py           # Desktop
uv run --with nicegui python nicegui_app.py     # Web
```

This avoids polluting the main project dependencies while allowing flexibility.

## Consequences

### Positive

- **Reduced onboarding friction**: New developers get working instances faster
- **Fewer support requests**: Self-documenting UI prevents common mistakes
- **Consistent configuration**: All instances get optimal setup
- **Flexible access**: Works in any context (SSH, local, CI)
- **Educational value**: Framework-specific READMEs teach modern Python UI development

### Negative

- **Maintenance burden**: Five UIs to keep in sync
- **Testing complexity**: Each interface needs testing
- **Dependency sprawl**: Multiple optional dependencies (though not installed by default)

### Mitigations

- Core logic is centralized in `command.py`
- Each UI is a thin wrapper around core logic
- Framework-specific code is isolated to single files
- Comprehensive READMEs reduce maintenance questions

## Related Decisions

- [ADR-0003: Prefer Python, Go, and TypeScript](0003-prefer-python-go-and-typescript-in-this-order.md) - This work uses Python as the primary language

## References

- [Typer Documentation](https://typer.tiangolo.com/)
- [Textual Documentation](https://textual.textualize.io/)
- [Trogon GitHub](https://github.com/Textualize/trogon)
- [Flet Documentation](https://flet.dev/)
- [NiceGUI Documentation](https://nicegui.io/)
- [GCP Provisioning First Steps Guide](../gcpprovisioningfirststeps.md)
