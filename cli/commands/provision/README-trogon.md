# Trogon Auto-TUI - CLI Explorer

Auto-generated TUI from CLI commands using [Trogon](https://github.com/Textualize/trogon) by Textualize.

## What is Trogon?

Trogon automatically generates a terminal UI from your Typer/Click CLI. No extra code needed - it introspects your CLI and builds a form-based interface.

**Zero effort TUI** - just add one line to your existing CLI:

```python
# That's it! This generates a full TUI
Trogon(app).run()
```

## Quick Start

```bash
# Launch auto-generated TUI
uv run --with typer --with trogon python run_trogon.py tui

# Or use as regular CLI
uv run --with typer --with trogon python run_trogon.py create my-notebook
uv run --with typer --with trogon python run_trogon.py --help
```

## Screenshot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ run_trogon.py                                                               │
├─────────────────────────────────────┬───────────────────────────────────────┤
│ Commands                            │  create                               │
│ ─────────────────────               │  ───────────────────────────────────  │
│ ▼ run_trogon.py                     │                                       │
│   ├── create                        │  Create a GCP instance with sane      │
│   ├── bootstrap                     │  defaults.                            │
│   ├── check                         │                                       │
│   ├── list-zones                    │  NAME (required)                      │
│   ├── list-machines                 │  [                              ]     │
│   └── tui                           │                                       │
│                                     │  --zone, -z                           │
│                                     │  [us-central1-a              ▼]       │
│                                     │                                       │
│                                     │  --machine-type, -m                   │
│                                     │  [e2-medium                  ▼]       │
│                                     │                                       │
│                                     │  --swap, -s                           │
│                                     │  [4                          ]        │
│                                     │                                       │
│                                     │  --optimize-dnf / --no-optimize-dnf   │
│                                     │  [✓]                                  │
├─────────────────────────────────────┴───────────────────────────────────────┤
│ ^r Close & Run │ ^t Focus Tree │ ^s Search │ q Quit                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How to Use

1. **Press `^t`** (Ctrl+T) to focus the command tree on the left
2. **Navigate with arrow keys:**
   - `↓` / `↑` - move between commands
   - `→` - expand to see subcommands
   - `Enter` - select a command
3. **Fill in the form** on the right side
4. **Press `^r`** (Ctrl+R) to execute the command

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `^t` | Focus command tree |
| `↑` / `↓` | Navigate commands |
| `→` / `←` | Expand/collapse |
| `Enter` | Select command |
| `Tab` | Navigate form fields |
| `^r` | Close TUI & run command |
| `^s` | Search commands |
| `^p` | Command palette |
| `q` | Quit |

## Known Issues

- **Don't press `^o`** before selecting a command - it crashes (Trogon bug)
- The TUI shows the command that would be executed at the bottom

---

# Trogon Coding Quickstart

## Installation

```bash
pip install typer trogon
# or
uv add typer trogon
```

## Hello World - Add TUI to Any Typer CLI

```python
import typer
from trogon import Trogon

app = typer.Typer()

@app.command()
def greet(name: str, excited: bool = False):
    """Greet someone."""
    greeting = f"Hello, {name}"
    if excited:
        greeting += "!"
    print(greeting)

@app.command()
def tui(ctx: typer.Context):
    """Open the TUI."""
    Trogon(app, click_context=ctx).run()

if __name__ == "__main__":
    app()
```

Run with:
```bash
python hello.py tui      # Opens TUI
python hello.py greet    # Normal CLI
```

## Core Concepts

### 1. Typer Basics (Trogon builds on Typer)

```python
import typer

app = typer.Typer(help="My awesome CLI")

@app.command()
def create(
    name: str = typer.Argument(..., help="Resource name"),
    count: int = typer.Option(1, "--count", "-c", help="Number to create"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Create a new resource."""
    for i in range(count):
        if verbose:
            print(f"Creating {name} ({i + 1}/{count})...")
        else:
            print(f"Created {name}")

if __name__ == "__main__":
    app()
```

### 2. Add Trogon with One Line

```python
import typer
from trogon import Trogon

app = typer.Typer()

@app.command()
def hello(name: str):
    print(f"Hello, {name}!")

@app.command()
def goodbye(name: str):
    print(f"Goodbye, {name}!")

# Add TUI command - that's it!
@app.command()
def tui(ctx: typer.Context):
    """Launch TUI."""
    Trogon(app, click_context=ctx).run()

if __name__ == "__main__":
    app()
```

### 3. Options with Choices (Dropdowns in TUI)

```python
import typer
from typing import Annotated
from enum import Enum

class Zone(str, Enum):
    US_CENTRAL = "us-central1-a"
    US_EAST = "us-east1-b"
    EUROPE = "europe-west1-b"

app = typer.Typer()

@app.command()
def deploy(
    name: str,
    zone: Annotated[Zone, typer.Option(help="GCP zone")] = Zone.US_CENTRAL,
):
    """Deploy to a zone."""
    print(f"Deploying {name} to {zone.value}")
```

In TUI, this renders as a dropdown!

### 4. Numeric Options (Sliders in TUI)

```python
import typer

app = typer.Typer()

@app.command()
def configure(
    memory: int = typer.Option(4, min=1, max=16, help="Memory in GB"),
    cpu: float = typer.Option(1.0, min=0.5, max=8.0, help="CPU cores"),
):
    """Configure resources."""
    print(f"Memory: {memory}GB, CPU: {cpu}")
```

### 5. Boolean Flags (Checkboxes in TUI)

```python
import typer

app = typer.Typer()

@app.command()
def run(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """Run with options."""
    print(f"verbose={verbose}, dry_run={dry_run}, force={force}")
```

### 6. Subcommands (Tree in TUI)

```python
import typer
from trogon import Trogon

app = typer.Typer()

# Subcommand group
db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")

@db_app.command()
def migrate():
    """Run migrations."""
    print("Migrating...")

@db_app.command()
def seed():
    """Seed database."""
    print("Seeding...")

# Another subcommand group
cache_app = typer.Typer(help="Cache operations")
app.add_typer(cache_app, name="cache")

@cache_app.command()
def clear():
    """Clear cache."""
    print("Clearing cache...")

@cache_app.command()
def warm():
    """Warm cache."""
    print("Warming cache...")

# TUI shows tree: app > db > [migrate, seed]
#                     > cache > [clear, warm]
@app.command()
def tui(ctx: typer.Context):
    Trogon(app, click_context=ctx).run()

if __name__ == "__main__":
    app()
```

### 7. Autocompletion (Works in CLI, Shows in TUI)

```python
import typer

ZONES = ["us-central1-a", "us-central1-b", "us-east1-b", "us-west1-a"]

def complete_zone(incomplete: str):
    for zone in ZONES:
        if zone.startswith(incomplete):
            yield zone

app = typer.Typer()

@app.command()
def deploy(
    zone: str = typer.Option(
        "us-central1-a",
        autocompletion=complete_zone,
        help="GCP zone",
    ),
):
    print(f"Deploying to {zone}")
```

### 8. Rich Output in CLI

```python
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
app = typer.Typer()

@app.command()
def status():
    """Show status with rich formatting."""
    table = Table(title="Resources")
    table.add_column("Name")
    table.add_column("Status")
    table.add_row("Instance 1", "[green]Running[/green]")
    table.add_row("Instance 2", "[red]Stopped[/red]")
    console.print(table)

@app.command()
def info():
    """Show info panel."""
    console.print(Panel(
        "This is important information",
        title="Info",
        border_style="blue",
    ))
```

### 9. Full Example: Provisioning CLI with TUI

```python
import typer
from trogon import Trogon
from rich.console import Console
from typing import Annotated

console = Console()
app = typer.Typer(
    name="provision",
    help="GCP instance provisioning CLI",
)

ZONES = ["us-central1-a", "us-central1-b", "us-east1-b"]
MACHINES = ["e2-small", "e2-medium", "e2-standard-2", "e2-standard-4"]

@app.command()
def create(
    name: Annotated[str, typer.Argument(help="Instance name")],
    zone: Annotated[str, typer.Option(
        "--zone", "-z",
        help="GCP zone",
        autocompletion=lambda: ZONES,
    )] = "us-central1-a",
    machine: Annotated[str, typer.Option(
        "--machine", "-m",
        help="Machine type",
        autocompletion=lambda: MACHINES,
    )] = "e2-medium",
    swap: Annotated[int, typer.Option(
        "--swap", "-s",
        help="Swap size in GB",
        min=1,
        max=16,
    )] = 4,
    optimize: Annotated[bool, typer.Option(
        "--optimize/--no-optimize",
        help="Optimize DNF",
    )] = True,
    dry_run: Annotated[bool, typer.Option(
        "--dry-run", "-n",
        help="Show what would be done",
    )] = False,
):
    """Create a new GCP instance."""
    console.print(f"[bold]Creating {name}[/bold]")
    console.print(f"  Zone: {zone}")
    console.print(f"  Machine: {machine}")
    console.print(f"  Swap: {swap}GB")
    console.print(f"  Optimize: {optimize}")
    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")

@app.command()
def list_zones():
    """List available zones."""
    for zone in ZONES:
        console.print(f"  • {zone}")

@app.command()
def tui(ctx: typer.Context):
    """Launch interactive TUI."""
    Trogon(app, click_context=ctx, app_name="provision").run()

if __name__ == "__main__":
    app()
```

## Trogon Options

```python
Trogon(
    app,                      # Your Typer/Click app
    click_context=ctx,        # Context from Typer
    app_name="myapp",         # Name shown in TUI
    command="tui",            # Command that launches TUI
).run()
```

## When to Use Trogon vs Custom TUI

| Use Trogon | Use Custom Textual TUI |
|------------|------------------------|
| Quick CLI exploration | Complex workflows |
| Existing CLI needs TUI | Custom layouts |
| Form-based input | Real-time updates |
| Minimal effort | Rich interactivity |

## Resources

- [Trogon GitHub](https://github.com/Textualize/trogon)
- [Typer Documentation](https://typer.tiangolo.com/)
- [Click Documentation](https://click.palletsprojects.com/)
- [Textual](https://textual.textualize.io/) (Trogon is built on Textual)
