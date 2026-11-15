# NiceGUI Web UI - Browser-Based Interface

A browser-based UI for GCP instance provisioning using the [NiceGUI](https://nicegui.io/) framework.

## What is NiceGUI?

NiceGUI is a Python framework for building web UIs that runs a local server and opens your browser. It uses:

- **Quasar Framework** (Vue.js) for components
- **FastAPI** backend for Python integration
- **WebSocket** for real-time updates
- **Material Design** styling

Perfect for engineering tools, dashboards, and control panels.

## Quick Start

```bash
# Start web server (auto-opens browser)
uv run --with nicegui python nicegui_app.py

# Opens http://localhost:8080
```

## Screenshot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🚀 GCP Instance Provisioning                              notebooks-cli    │
├─────────────────────────────────────┬───────────────────────────────────────┤
│  Instance Configuration             │  Provisioning Log                     │
│  ───────────────────────────────    │  ─────────────────────────────────    │
│  Instance Name                      │  ┌─────────────────────────────────┐  │
│  [my-notebook                   ]   │  │ 🚀 Creating instance...         │  │
│                                     │  │ ⚙️  Configuring swap (4GB)       │  │
│  Zone                               │  │ 📦 Optimizing DNF               │  │
│  [us-central1-a                 ▼]  │  │ ✅ Done!                         │  │
│                                     │  │                                 │  │
│  Machine Type                       │  │                                 │  │
│  [e2-medium (4GB) ✓ Recommended ▼]  │  │                                 │  │
│                                     │  │                                 │  │
│  Swap Size: 4GB                     │  │                                 │  │
│  1 [━━━━━━━━━━●━━━━━━━━━━━━━] 16    │  │                                 │  │
│                                     │  │                                 │  │
│  [✓] Optimize DNF repositories      │  └─────────────────────────────────┘  │
│                                     │                                       │
│  [ 🚀 CREATE INSTANCE ]             │                                       │
└─────────────────────────────────────┴───────────────────────────────────────┘
```

## Features

- Modern web UI without JavaScript coding
- Real-time log streaming via WebSocket
- Works with SSH port forwarding
- Dark theme support
- Snackbar notifications

## Remote Access

```bash
# On remote machine
uv run --with nicegui python nicegui_app.py

# On local machine (port forward)
ssh -L 8080:localhost:8080 user@remote-host

# Open http://localhost:8080 locally
```

---

# NiceGUI Coding Quickstart

## Installation

```bash
pip install nicegui
# or
uv add nicegui
```

## Hello World

```python
from nicegui import ui

ui.label('Hello, World!')

ui.run()
```

Run with:
```bash
python hello.py
# Opens browser at http://localhost:8080
```

## Core Concepts

### 1. Basic Elements

```python
from nicegui import ui

# Text
ui.label('This is a label')
ui.markdown('**Bold** and *italic*')
ui.html('<b>Raw HTML</b>')

# Inputs
ui.input(label='Name', placeholder='Enter name')
ui.number(label='Age', value=25)
ui.textarea(label='Description')

# Buttons
ui.button('Click me', on_click=lambda: ui.notify('Clicked!'))

ui.run()
```

### 2. Event Handling

```python
from nicegui import ui

name_input = ui.input(label='Name')
greeting = ui.label()

def greet():
    greeting.text = f'Hello, {name_input.value}!'

ui.button('Greet', on_click=greet)

ui.run()
```

### 3. Layouts

```python
from nicegui import ui

# Row (horizontal)
with ui.row():
    ui.label('Left')
    ui.label('Center')
    ui.label('Right')

# Column (vertical)
with ui.column():
    ui.label('Top')
    ui.label('Middle')
    ui.label('Bottom')

# Card
with ui.card():
    ui.label('Card Title').classes('text-h6')
    ui.label('Card content goes here')
    ui.button('Action')

# Grid
with ui.grid(columns=3):
    for i in range(9):
        ui.label(f'Cell {i}')

ui.run()
```

### 4. Styling with Tailwind CSS

NiceGUI uses Tailwind CSS classes:

```python
from nicegui import ui

# Text styling
ui.label('Large Bold').classes('text-2xl font-bold')
ui.label('Colored').classes('text-blue-500')

# Spacing
ui.label('Padded').classes('p-4 m-2')

# Background
with ui.card().classes('bg-gray-800 text-white'):
    ui.label('Dark card')

# Flexbox
with ui.row().classes('gap-4 items-center justify-between w-full'):
    ui.label('Left')
    ui.label('Right')

ui.run()
```

### 5. Common Components

```python
from nicegui import ui

# Select dropdown
zone = ui.select(
    label='Zone',
    options=['us-central1-a', 'us-east1-b', 'europe-west1-b'],
    value='us-central1-a',
)

# Slider
swap = ui.slider(min=1, max=16, value=4).props('label-always')
ui.label().bind_text_from(swap, 'value', lambda v: f'Swap: {v}GB')

# Checkbox
optimize = ui.checkbox('Optimize DNF', value=True)

# Switch
dark_mode = ui.switch('Dark mode')

# Toggle buttons
toggle = ui.toggle(['Option A', 'Option B', 'Option C'], value='Option A')

# Radio buttons
radio = ui.radio(['Small', 'Medium', 'Large'], value='Medium')

ui.run()
```

### 6. Two-Column Layout (like our app)

```python
from nicegui import ui

# Dark theme
ui.dark_mode().enable()

# Header
with ui.header().classes('bg-blue-600'):
    ui.label('My Application').classes('text-xl font-bold')

# Main content
with ui.row().classes('w-full gap-4 p-4'):
    # Left card - form
    with ui.card().classes('w-1/2'):
        ui.label('Configuration').classes('text-lg font-bold')
        ui.separator()
        
        name = ui.input(label='Instance Name')
        zone = ui.select(label='Zone', options=['us-central1-a', 'us-east1-b'])
        swap = ui.slider(min=1, max=16, value=4)
        optimize = ui.checkbox('Optimize', value=True)
        
        ui.button('Submit', on_click=lambda: ui.notify('Submitted!'))
    
    # Right card - output
    with ui.card().classes('w-1/2'):
        ui.label('Output').classes('text-lg font-bold')
        ui.separator()
        
        log = ui.log(max_lines=20).classes('w-full h-64')
        log.push('Ready...')

ui.run()
```

### 7. Async Operations

```python
from nicegui import ui
import asyncio

log = ui.log(max_lines=10)

async def long_task():
    for i in range(5):
        log.push(f'Step {i + 1}/5...')
        await asyncio.sleep(1)
    log.push('Done!')
    ui.notify('Task completed!', type='positive')

ui.button('Start Task', on_click=long_task)

ui.run()
```

### 8. Dialogs and Notifications

```python
from nicegui import ui

# Snackbar notifications
def notify_examples():
    ui.notify('Info message')
    ui.notify('Success!', type='positive')
    ui.notify('Warning!', type='warning')
    ui.notify('Error!', type='negative')

ui.button('Show Notifications', on_click=notify_examples)

# Dialog
with ui.dialog() as dialog, ui.card():
    ui.label('Are you sure?')
    with ui.row():
        ui.button('Cancel', on_click=dialog.close)
        ui.button('Confirm', on_click=lambda: (dialog.close(), ui.notify('Confirmed!')))

ui.button('Show Dialog', on_click=dialog.open)

ui.run()
```

### 9. Binding Values

```python
from nicegui import ui

class Model:
    name = ''
    count = 0

model = Model()

# Two-way binding
ui.input('Name').bind_value(model, 'name')
ui.label().bind_text_from(model, 'name', lambda n: f'Hello, {n}!')

# One-way binding
ui.slider(min=0, max=100).bind_value(model, 'count')
ui.linear_progress().bind_value_from(model, 'count', lambda c: c / 100)

ui.run()
```

### 10. Running Subprocesses

```python
from nicegui import ui
import asyncio

log = ui.log(max_lines=50).classes('w-full h-96 font-mono')

async def run_command():
    log.clear()
    log.push('$ ls -la')
    
    proc = await asyncio.create_subprocess_shell(
        'ls -la',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        log.push(line.decode().rstrip())
    
    await proc.wait()
    log.push(f'\nExit code: {proc.returncode}')

ui.button('Run ls -la', on_click=run_command)

ui.run()
```

## Useful Components

| Component | Purpose |
|-----------|---------|
| `ui.label` | Display text |
| `ui.input` | Text input |
| `ui.number` | Numeric input |
| `ui.select` | Dropdown select |
| `ui.slider` | Range slider |
| `ui.checkbox` | Boolean checkbox |
| `ui.switch` | Toggle switch |
| `ui.button` | Action button |
| `ui.card` | Material card |
| `ui.row` | Horizontal layout |
| `ui.column` | Vertical layout |
| `ui.log` | Scrollable log output |
| `ui.table` | Data table |
| `ui.notify` | Toast notification |
| `ui.dialog` | Modal dialog |
| `ui.header` | Page header |
| `ui.footer` | Page footer |

## Configuration

```python
from nicegui import ui

ui.run(
    port=8080,              # Port number
    title='My App',         # Browser tab title
    dark=True,              # Dark mode
    reload=True,            # Hot reload (dev)
    show=True,              # Auto-open browser
    binding_refresh_interval=0.1,  # Binding update rate
)
```

## Deployment

```bash
# Run in production
python app.py

# Or with uvicorn for more control
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Resources

- [NiceGUI Documentation](https://nicegui.io/documentation)
- [Examples](https://nicegui.io/documentation#examples)
- [GitHub](https://github.com/zauberzeug/nicegui)
- [Quasar Components](https://quasar.dev/vue-components) (underlying UI library)
- [Tailwind CSS](https://tailwindcss.com/docs) (for styling)
