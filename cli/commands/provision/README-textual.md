# Textual TUI - Terminal User Interface

A full-featured terminal UI for GCP instance provisioning using the [Textual](https://textual.textualize.io/) framework.

## What is Textual?

Textual is a Python framework for building rich terminal applications. Built by the creators of [Rich](https://rich.readthedocs.io/), it provides:

- **60fps rendering** with smooth animations
- **CSS-like styling** for layout and theming
- **Mouse support** in modern terminals
- **Async-first** architecture for responsive UIs
- **Works over SSH** - no X11/GUI required

## Quick Start

```bash
# Run the TUI
uv run --with textual python run_tui.py
```

## Screenshot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🚀 GCP Instance Provisioning                                         15:42 │
├─────────────────────────────────────┬───────────────────────────────────────┤
│ Instance Configuration              │ 📋 Provisioning Log                   │
│ ─────────────────────────────────── │ ───────────────────────────────────── │
│ Instance Name: [my-notebook      ]  │ > Creating instance...                │
│ Zone:          [us-central1-a    ▼] │ > Configuring swap (4GB)              │
│ Machine Type:  [e2-medium (4GB)  ▼] │ > Optimizing DNF repos                │
│ Swap Size:     [████████░░] 4GB     │ > ✅ Done!                             │
│ [✓] Optimize DNF                    │                                       │
│                                     │                                       │
│ [ 🚀 Create Instance ]              │                                       │
├─────────────────────────────────────┴───────────────────────────────────────┤
│ esc Quit │ ^p Palette │ Tab Navigate                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Navigate between fields |
| `Enter` | Activate button / Select dropdown item |
| `↑` / `↓` | Navigate dropdown options |
| `Space` | Toggle checkbox/switch |
| `Esc` | Close dropdown / Quit app |
| `^p` | Open command palette |

## Requirements

- Python 3.8+
- Modern terminal (iTerm2, Ghostty, Kitty, WezTerm, Terminal.app)
- Works in tmux/screen
- Works over SSH

---

# Textual Coding Quickstart

## Installation

```bash
pip install textual
# or
uv add textual
```

## Hello World

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

class HelloApp(App):
    """A simple Textual app."""
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Hello, World!")
        yield Footer()

if __name__ == "__main__":
    app = HelloApp()
    app.run()
```

Run with:
```bash
python hello.py
```

## Core Concepts

### 1. Apps and Widgets

Every Textual app inherits from `App`. Widgets are UI components.

```python
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label

class MyApp(App):
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Label("Enter your name:")
        yield Input(placeholder="Name", id="name-input")
        yield Button("Submit", id="submit-btn")
```

### 2. Event Handling

Use decorators to handle events:

```python
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static

class MyApp(App):
    def compose(self) -> ComposeResult:
        yield Input(id="name")
        yield Button("Greet", id="greet")
        yield Static(id="output")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Called when any button is pressed."""
        if event.button.id == "greet":
            name = self.query_one("#name", Input).value
            self.query_one("#output", Static).update(f"Hello, {name}!")
```

### 3. Layouts with Containers

```python
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

class LayoutApp(App):
    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("Sidebar")
                yield Button("Option 1")
                yield Button("Option 2")
            with Vertical(id="main"):
                yield Static("Main Content Area")
```

### 4. CSS Styling

Create a `.tcss` file (Textual CSS):

```css
/* styles.tcss */
Screen {
    layout: grid;
    grid-size: 2 1;
}

#sidebar {
    width: 30;
    background: $primary-background;
}

#main {
    background: $surface;
}

Button {
    margin: 1;
}

Button:hover {
    background: $accent;
}
```

Load it in your app:

```python
class MyApp(App):
    CSS_PATH = "styles.tcss"
```

### 5. Async Operations

Textual is async-first. Use `@work` for background tasks:

```python
from textual.app import App, ComposeResult
from textual.widgets import Button, Log
from textual import work
import asyncio

class AsyncApp(App):
    def compose(self) -> ComposeResult:
        yield Button("Start Task", id="start")
        yield Log(id="log")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.run_long_task()
    
    @work(exclusive=True)
    async def run_long_task(self) -> None:
        """Runs in background, doesn't block UI."""
        log = self.query_one("#log", Log)
        for i in range(5):
            log.write_line(f"Step {i + 1}/5...")
            await asyncio.sleep(1)
        log.write_line("Done!")
```

### 6. Custom Widgets

```python
from textual.widget import Widget
from textual.reactive import reactive

class Counter(Widget):
    """A custom counter widget."""
    
    count: reactive[int] = reactive(0)
    
    def render(self) -> str:
        return f"Count: {self.count}"
    
    def increment(self) -> None:
        self.count += 1

class MyApp(App):
    def compose(self) -> ComposeResult:
        yield Counter(id="counter")
        yield Button("Increment", id="inc")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.query_one("#counter", Counter).increment()
```

### 7. Select/Dropdown Widget

```python
from textual.app import App, ComposeResult
from textual.widgets import Select, Static

ZONES = [
    ("US Central", "us-central1-a"),
    ("US East", "us-east1-b"),
    ("Europe West", "europe-west1-b"),
]

class SelectApp(App):
    def compose(self) -> ComposeResult:
        yield Select(ZONES, prompt="Select Zone", id="zone")
        yield Static(id="output")
    
    def on_select_changed(self, event: Select.Changed) -> None:
        self.query_one("#output", Static).update(f"Selected: {event.value}")
```

## Useful Widgets

| Widget | Purpose |
|--------|---------|
| `Header` | App header with title and clock |
| `Footer` | Shows key bindings |
| `Button` | Clickable button |
| `Input` | Text input field |
| `Select` | Dropdown select |
| `Switch` | Toggle switch |
| `Checkbox` | Checkbox |
| `DataTable` | Sortable data table |
| `Log` | Scrollable log output |
| `ProgressBar` | Progress indicator |
| `Tree` | Hierarchical tree view |
| `Markdown` | Render markdown |
| `Static` | Static text/content |

## Development Tools

```bash
# Run with live reload
textual run --dev my_app.py

# Open console for debugging
textual console

# Run with CSS debugging
textual run --dev --css-path styles.tcss my_app.py
```

## Resources

- [Textual Documentation](https://textual.textualize.io/)
- [Widget Gallery](https://textual.textualize.io/widget_gallery/)
- [Tutorial](https://textual.textualize.io/tutorial/)
- [GitHub](https://github.com/Textualize/textual)
