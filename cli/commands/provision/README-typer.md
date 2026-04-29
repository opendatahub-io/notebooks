# Typer CLI - Command Line Interface

A command-line interface for GCP instance provisioning using [Typer](https://typer.tiangolo.com/).

## What is Typer?

Typer is a modern Python library for building CLI applications. Built on Click, it uses Python type hints for:

- **Automatic argument parsing**
- **Shell autocompletion** (bash, zsh, fish, PowerShell)
- **Beautiful help pages** via Rich
- **Type validation**

## Quick Start

```bash
# See all commands
uv run --with typer python run_cli.py --help

# Create an instance
uv run --with typer python run_cli.py create my-notebook --zone us-central1-a

# Use the wrapper script
./provision create my-notebook --zone us-central1-a
```

## Commands

### `create` - Create a new instance

```bash
# Basic usage
./provision create my-notebook

# With all options
./provision create my-notebook \
    --zone us-central1-a \
    --machine-type e2-medium \
    --swap 4 \
    --optimize-dnf

# Dry run (show what would happen)
./provision create my-notebook --dry-run
```

Options:
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--zone` | `-z` | `us-central1-a` | GCP zone |
| `--machine-type` | `-m` | `e2-medium` | Machine type |
| `--swap` | `-s` | `4` | Swap size in GB (1-16) |
| `--optimize-dnf` | | `True` | Optimize DNF repos |
| `--dry-run` | `-n` | `False` | Show without executing |

### `bootstrap` - Configure existing instance

```bash
./provision bootstrap my-notebook --zone us-central1-a --swap 8
```

### `check` - Verify instance configuration

```bash
./provision check my-notebook --zone us-central1-a
```

### `tui` - Launch interactive TUI

```bash
./provision tui  # Requires textual
```

## Shell Completion

```bash
# Install for zsh
./provision --install-completion zsh
source ~/.zshrc

# Now tab-completion works
./provision create <TAB>
./provision create my-instance --zone <TAB>
```

## Wrapper Script

The `provision` script handles `uv` and dependencies:

```bash
# Make executable (already done)
chmod +x provision

# Add to PATH
export PATH="$PATH:$(pwd)"

# Use from anywhere
provision create my-notebook
```

---

# Typer Coding Quickstart

## Installation

```bash
pip install typer[all]  # Includes rich for pretty output
# or
uv add typer rich
```

## Hello World

```python
import typer

def main(name: str):
    print(f"Hello, {name}!")

if __name__ == "__main__":
    typer.run(main)
```

Run:
```bash
python hello.py World
# Output: Hello, World!
```

## Core Concepts

### 1. Basic App with Commands

```python
import typer

app = typer.Typer()

@app.command()
def hello(name: str):
    """Say hello to NAME."""
    print(f"Hello, {name}!")

@app.command()
def goodbye(name: str):
    """Say goodbye to NAME."""
    print(f"Goodbye, {name}!")

if __name__ == "__main__":
    app()
```

Usage:
```bash
python app.py hello World
python app.py goodbye World
python app.py --help
```

### 2. Arguments vs Options

```python
import typer

app = typer.Typer()

@app.command()
def create(
    # Argument - positional, required by default
    name: str = typer.Argument(..., help="Resource name"),
    
    # Option - named, optional with default
    count: int = typer.Option(1, "--count", "-c", help="Number to create"),
    
    # Flag - boolean option
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Create resources."""
    for i in range(count):
        if verbose:
            print(f"Creating {name} ({i + 1}/{count})...")
        print(f"Created: {name}")

if __name__ == "__main__":
    app()
```

Usage:
```bash
python app.py create myresource              # name=myresource, count=1, verbose=False
python app.py create myresource -c 3         # count=3
python app.py create myresource -c 3 -v      # verbose=True
```

### 3. Type Hints for Validation

```python
import typer
from typing import Optional
from enum import Enum
from pathlib import Path

class Color(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

app = typer.Typer()

@app.command()
def process(
    # Enum - creates choices
    color: Color = typer.Option(Color.RED, help="Choose a color"),
    
    # Path - validates file exists
    config: Path = typer.Option(..., exists=True, help="Config file"),
    
    # Optional - can be None
    name: Optional[str] = typer.Option(None, help="Optional name"),
    
    # Int with bounds
    count: int = typer.Option(1, min=1, max=100, help="Count (1-100)"),
):
    print(f"Color: {color.value}, Config: {config}, Name: {name}, Count: {count}")

if __name__ == "__main__":
    app()
```

### 4. Autocompletion

```python
import typer

ZONES = ["us-central1-a", "us-central1-b", "us-east1-b", "us-west1-a"]

def complete_zone(incomplete: str):
    """Return matching zones for autocompletion."""
    for zone in ZONES:
        if zone.startswith(incomplete):
            yield zone

app = typer.Typer()

@app.command()
def deploy(
    zone: str = typer.Option(
        "us-central1-a",
        "--zone", "-z",
        help="GCP zone",
        autocompletion=complete_zone,
    ),
):
    print(f"Deploying to {zone}")

if __name__ == "__main__":
    app()
```

Install completion:
```bash
python app.py --install-completion zsh
source ~/.zshrc
python app.py deploy --zone <TAB>
```

### 5. Rich Output

```python
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track

console = Console()
app = typer.Typer()

@app.command()
def status():
    """Show status table."""
    table = Table(title="Resources")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_row("Instance 1", "[green]Running[/green]")
    table.add_row("Instance 2", "[red]Stopped[/red]")
    console.print(table)

@app.command()
def process(count: int = 100):
    """Show progress bar."""
    for _ in track(range(count), description="Processing..."):
        pass  # Do work here
    console.print("[green]Done![/green]")

@app.command()
def info():
    """Show info panel."""
    console.print(Panel(
        "[bold]Important Information[/bold]\n\n"
        "This is a multi-line\n"
        "information panel.",
        title="Info",
        border_style="blue",
    ))

if __name__ == "__main__":
    app()
```

### 6. Subcommands (Command Groups)

```python
import typer

app = typer.Typer(help="Main application")

# Subcommand group: db
db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")

@db_app.command()
def migrate():
    """Run database migrations."""
    print("Running migrations...")

@db_app.command()
def seed():
    """Seed the database."""
    print("Seeding database...")

# Subcommand group: cache
cache_app = typer.Typer(help="Cache operations")
app.add_typer(cache_app, name="cache")

@cache_app.command()
def clear():
    """Clear the cache."""
    print("Clearing cache...")

if __name__ == "__main__":
    app()
```

Usage:
```bash
python app.py --help           # Show main help
python app.py db --help        # Show db subcommands
python app.py db migrate       # Run migration
python app.py cache clear      # Clear cache
```

### 7. Callbacks and Context

```python
import typer
from typing import Optional

app = typer.Typer()

@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """
    Main callback - runs before any command.
    Use for global options.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

@app.command()
def process(ctx: typer.Context, name: str):
    """Process something."""
    if ctx.obj["verbose"]:
        print(f"Verbose: Processing {name}")
    print(f"Processed: {name}")

if __name__ == "__main__":
    app()
```

Usage:
```bash
python app.py -v process myname  # Global verbose flag
```

### 8. Confirmation Prompts

```python
import typer

app = typer.Typer()

@app.command()
def delete(
    name: str,
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a resource."""
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete {name}?")
        if not confirm:
            print("Cancelled.")
            raise typer.Abort()
    
    print(f"Deleted: {name}")

@app.command()
def configure():
    """Interactive configuration."""
    name = typer.prompt("Enter name")
    password = typer.prompt("Enter password", hide_input=True)
    count = typer.prompt("Enter count", type=int, default=10)
    
    print(f"Configured: {name}, count={count}")

if __name__ == "__main__":
    app()
```

### 9. Error Handling

```python
import typer

app = typer.Typer()

@app.command()
def process(name: str):
    if name == "invalid":
        # Exit with error
        raise typer.Exit(code=1)
    
    if name == "abort":
        # Abort with message
        raise typer.Abort()
    
    if name == "bad":
        # Show error and exit
        typer.echo("Error: Bad name!", err=True)
        raise typer.Exit(code=1)
    
    print(f"Processed: {name}")

if __name__ == "__main__":
    app()
```

### 10. Full Example: Provisioning CLI

```python
import typer
from rich.console import Console
from rich.panel import Panel
from typing import Annotated

console = Console()

app = typer.Typer(
    name="provision",
    help="GCP instance provisioning CLI",
    no_args_is_help=True,
)

ZONES = ["us-central1-a", "us-central1-b", "us-east1-b"]
MACHINES = ["e2-small", "e2-medium", "e2-standard-2"]
BLOCKED = {"e2-micro", "f1-micro", "g1-small"}

def validate_machine(value: str) -> str:
    if value in BLOCKED:
        raise typer.BadParameter(f"{value} is too small. Use: {', '.join(MACHINES)}")
    return value

@app.command()
def create(
    name: Annotated[str, typer.Argument(help="Instance name")],
    zone: Annotated[str, typer.Option(
        "--zone", "-z",
        help="GCP zone",
        autocompletion=lambda: ZONES,
    )] = "us-central1-a",
    machine_type: Annotated[str, typer.Option(
        "--machine-type", "-m",
        help="Machine type (e2-micro blocked)",
        autocompletion=lambda: MACHINES,
        callback=validate_machine,
    )] = "e2-medium",
    swap_gb: Annotated[int, typer.Option(
        "--swap", "-s",
        help="Swap size in GB",
        min=1, max=16,
    )] = 4,
    optimize_dnf: Annotated[bool, typer.Option(
        "--optimize-dnf/--no-optimize-dnf",
        help="Optimize DNF repos",
    )] = True,
    dry_run: Annotated[bool, typer.Option(
        "--dry-run", "-n",
        help="Show what would be done",
    )] = False,
):
    """Create a GCP instance with sane defaults."""
    console.print(Panel(
        f"[bold green]Creating instance:[/bold green] {name}\n"
        f"Zone: {zone}\n"
        f"Machine: {machine_type}\n"
        f"Swap: {swap_gb}GB\n"
        f"DNF Optimization: {'✓' if optimize_dnf else '✗'}",
        title="Configuration",
    ))
    
    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")
        return
    
    # Do actual work here
    console.print("[green]✓ Instance created![/green]")

@app.command()
def bootstrap(
    name: Annotated[str, typer.Argument(help="Instance name")],
    zone: Annotated[str, typer.Option("--zone", "-z")] = "us-central1-a",
    swap_gb: Annotated[int, typer.Option("--swap", "-s", min=1, max=16)] = 4,
):
    """Bootstrap an existing instance with swap and DNF optimizations."""
    console.print(f"Bootstrapping {name} in {zone}...")
    console.print(f"Configuring {swap_gb}GB swap and optimizing DNF.")

@app.command()
def check(
    name: Annotated[str, typer.Argument(help="Instance name")],
    zone: Annotated[str, typer.Option("--zone", "-z")] = "us-central1-a",
):
    """Check instance configuration."""
    console.print(f"Checking {name} in {zone}...")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    """GCP Instance Provisioning CLI."""
    if version:
        console.print("provision v0.1.0")
        raise typer.Exit()

if __name__ == "__main__":
    app()
```

## Useful Patterns

| Pattern | Code |
|---------|------|
| Required argument | `name: str = typer.Argument(...)` |
| Optional argument | `name: str = typer.Argument("default")` |
| Required option | `--name: str = typer.Option(...)` |
| Optional option | `--name: str = typer.Option("default")` |
| Boolean flag | `--verbose: bool = typer.Option(False, "--verbose", "-v")` |
| Boolean pair | `--flag/--no-flag: bool = typer.Option(True)` |
| Enum choices | `color: Color = typer.Option(Color.RED)` |
| Bounded int | `count: int = typer.Option(1, min=1, max=100)` |
| File path | `config: Path = typer.Option(..., exists=True)` |
| Multiple values | `names: List[str] = typer.Option([])` |
| Prompt user | `typer.prompt("Enter value")` |
| Confirm | `typer.confirm("Are you sure?")` |
| Exit with code | `raise typer.Exit(code=1)` |

## Resources

- [Typer Documentation](https://typer.tiangolo.com/)
- [Click Documentation](https://click.palletsprojects.com/) (Typer is built on Click)
- [Rich Documentation](https://rich.readthedocs.io/) (for pretty output)
- [GitHub](https://github.com/tiangolo/typer)
