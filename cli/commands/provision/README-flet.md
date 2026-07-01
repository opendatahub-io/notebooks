# Flet Desktop App - Flutter/Skia GUI

A native desktop application for GCP instance provisioning using the [Flet](https://flet.dev/) framework (Flutter for Python).

## What is Flet?

Flet lets you build Flutter apps in Python - no Dart required. It uses:

- **Flutter engine** for rendering (same as Flutter mobile/web apps)
- **Skia/Impeller** graphics engine (GPU-accelerated, 60fps)
- **Material Design 3** components out of the box
- **Cross-platform** - same code runs on macOS, Linux, Windows, web, mobile

## Quick Start

```bash
# Run desktop app
uv run --with flet python flet_app.py

# Or run as web app (opens browser)
uv run --with flet flet run --web flet_app.py
```

## Screenshot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ● ● ●                    GCP Instance Provisioning                          │
├─────────────────────────────────────┬───────────────────────────────────────┤
│  ╭─────────────────────────────╮    │  ╭─────────────────────────────────╮  │
│  │ 📦 Instance Name            │    │  │ 📋 Provisioning Log             │  │
│  │ [my-notebook            ]   │    │  │                                 │  │
│  │                             │    │  │ 🚀 Creating instance...         │  │
│  │ 🌍 Zone                     │    │  │ ⚙️  Configuring swap (4GB)       │  │
│  │ [us-central1-a          ▼]  │    │  │ 📦 Optimizing DNF               │  │
│  │                             │    │  │ ✅ Done!                         │  │
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

## Features

- Native window with system decorations
- GPU-accelerated rendering
- Smooth animations (60fps)
- Dark/light theme support
- Same code works as web app

## Notes

- **First run is slow** - downloads Flutter runtime (~100MB, cached)
- **Requires display** - won't work over SSH without X11
- **GPU recommended** - falls back to software rendering

---

# Flet Coding Quickstart

## Installation

```bash
pip install flet
# or
uv add flet
```

## Hello World

```python
import flet as ft

def main(page: ft.Page):
    page.title = "Hello Flet"
    page.add(ft.Text("Hello, World!"))

ft.app(main)
```

Run with:
```bash
python hello.py
# Or as web app:
flet run --web hello.py
```

## Core Concepts

### 1. Pages and Controls

The `page` is your canvas. Add controls (widgets) to it:

```python
import flet as ft

def main(page: ft.Page):
    page.title = "My App"
    page.theme_mode = ft.ThemeMode.DARK
    
    # Add controls
    page.add(
        ft.Text("Welcome!", size=30, weight=ft.FontWeight.BOLD),
        ft.TextField(label="Your name"),
        ft.ElevatedButton("Submit"),
    )

ft.app(main)
```

### 2. Event Handling

```python
import flet as ft

def main(page: ft.Page):
    name_field = ft.TextField(label="Name")
    greeting = ft.Text()
    
    def greet_clicked(e):
        greeting.value = f"Hello, {name_field.value}!"
        page.update()  # Refresh UI
    
    page.add(
        name_field,
        ft.ElevatedButton("Greet", on_click=greet_clicked),
        greeting,
    )

ft.app(main)
```

### 3. Layouts

```python
import flet as ft

def main(page: ft.Page):
    # Row - horizontal layout
    row = ft.Row([
        ft.Text("Left"),
        ft.Text("Center"),
        ft.Text("Right"),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
    
    # Column - vertical layout
    column = ft.Column([
        ft.Text("Top"),
        ft.Text("Middle"),
        ft.Text("Bottom"),
    ])
    
    # Container with styling
    card = ft.Container(
        content=ft.Column([
            ft.Text("Card Title", size=20),
            ft.Text("Card content goes here"),
        ]),
        bgcolor=ft.colors.SURFACE_VARIANT,
        border_radius=10,
        padding=20,
    )
    
    page.add(row, ft.Divider(), column, ft.Divider(), card)

ft.app(main)
```

### 4. Common Controls

```python
import flet as ft

def main(page: ft.Page):
    # Text input
    text_field = ft.TextField(
        label="Instance Name",
        prefix_icon=ft.icons.COMPUTER,
        hint_text="e.g., my-notebook",
    )
    
    # Dropdown
    dropdown = ft.Dropdown(
        label="Zone",
        options=[
            ft.dropdown.Option("us-central1-a", "US Central"),
            ft.dropdown.Option("us-east1-b", "US East"),
            ft.dropdown.Option("europe-west1-b", "Europe West"),
        ],
        value="us-central1-a",
    )
    
    # Slider
    slider = ft.Slider(
        min=1,
        max=16,
        value=4,
        divisions=15,
        label="{value}GB",
    )
    
    # Switch
    switch = ft.Switch(label="Enable feature", value=True)
    
    # Checkbox
    checkbox = ft.Checkbox(label="I agree", value=False)
    
    # Button variants
    buttons = ft.Row([
        ft.ElevatedButton("Elevated"),
        ft.FilledButton("Filled"),
        ft.OutlinedButton("Outlined"),
        ft.TextButton("Text"),
        ft.IconButton(ft.icons.SETTINGS),
    ])
    
    page.add(text_field, dropdown, slider, switch, checkbox, buttons)

ft.app(main)
```

### 5. Async Operations

```python
import flet as ft
import asyncio

def main(page: ft.Page):
    log = ft.TextField(
        multiline=True,
        read_only=True,
        min_lines=10,
        max_lines=10,
    )
    
    async def run_task(e):
        for i in range(5):
            log.value = (log.value or "") + f"Step {i + 1}/5...\n"
            page.update()
            await asyncio.sleep(1)
        log.value += "Done!\n"
        page.update()
    
    page.add(
        ft.ElevatedButton("Start Task", on_click=run_task),
        log,
    )

ft.app(main)
```

### 6. Two-Column Layout (like our app)

```python
import flet as ft

def main(page: ft.Page):
    page.title = "Two Column Layout"
    page.theme_mode = ft.ThemeMode.DARK
    
    # Left column - form
    left_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Text("Configuration", size=20, weight=ft.FontWeight.BOLD),
                ft.TextField(label="Name"),
                ft.Dropdown(
                    label="Option",
                    options=[ft.dropdown.Option("a"), ft.dropdown.Option("b")],
                ),
                ft.ElevatedButton("Submit", icon=ft.icons.SEND),
            ]),
            padding=20,
        ),
        expand=True,
    )
    
    # Right column - output
    right_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Text("Output", size=20, weight=ft.FontWeight.BOLD),
                ft.TextField(
                    multiline=True,
                    read_only=True,
                    min_lines=15,
                    value="Ready...",
                ),
            ]),
            padding=20,
        ),
        expand=True,
    )
    
    # Layout
    page.add(
        ft.Row(
            [left_card, right_card],
            expand=True,
            spacing=20,
        )
    )

ft.app(main)
```

### 7. Dialogs and Snackbars

```python
import flet as ft

def main(page: ft.Page):
    def show_dialog(e):
        dialog = ft.AlertDialog(
            title=ft.Text("Confirm"),
            content=ft.Text("Are you sure?"),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: page.close(dialog)),
                ft.TextButton("OK", on_click=lambda e: page.close(dialog)),
            ],
        )
        page.open(dialog)
    
    def show_snackbar(e):
        page.open(ft.SnackBar(
            content=ft.Text("Operation completed!"),
            action="Undo",
        ))
    
    page.add(
        ft.ElevatedButton("Show Dialog", on_click=show_dialog),
        ft.ElevatedButton("Show Snackbar", on_click=show_snackbar),
    )

ft.app(main)
```

## Useful Controls

| Control | Purpose |
|---------|---------|
| `Text` | Display text |
| `TextField` | Text input |
| `Dropdown` | Select from options |
| `Slider` | Numeric range input |
| `Switch` | Toggle on/off |
| `Checkbox` | Boolean option |
| `ElevatedButton` | Primary action button |
| `IconButton` | Icon-only button |
| `Card` | Material card container |
| `Container` | Styled container |
| `Row` | Horizontal layout |
| `Column` | Vertical layout |
| `DataTable` | Tabular data |
| `ProgressBar` | Progress indicator |
| `ProgressRing` | Circular progress |
| `AlertDialog` | Modal dialog |
| `SnackBar` | Toast notification |

## Run Modes

```bash
# Desktop app (default)
python app.py
flet run app.py

# Web app (opens browser)
flet run --web app.py

# Web app on specific port
flet run --web --port 8080 app.py

# Hot reload during development
flet run -r app.py
```

## Packaging

```bash
# Package as standalone executable
flet pack app.py

# Creates: dist/app (macOS), dist/app.exe (Windows)
```

## Resources

- [Flet Documentation](https://flet.dev/docs/)
- [Controls Reference](https://flet.dev/docs/controls)
- [Tutorials](https://flet.dev/docs/tutorials)
- [GitHub](https://github.com/flet-dev/flet)
- [Examples Gallery](https://flet.dev/docs/tutorials/python-todo)
