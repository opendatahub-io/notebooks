# DEVELOPMENT.md: ODH Notebooks CLI

This guide explains the architecture, design patterns, and how to extend the CLI with new functionality.

## Architecture Overview

The CLI follows a modular design with three main concerns:

1. **Entry & Argument Parsing** - Captures user input
2. **Command/Handler Loading** - Dynamically loads executable commands
3. **Execution** - Runs specific operations (compile, build, etc.)

### High-Level Flow

```
User Input (CLI arguments)
         ↓
Parser (argparse)
         ↓
Autoloader (finds commands/handlers)
         ↓
Handler/Command Class (executes logic)
         ↓
Output (generated files, status, etc.)
```

## Directory Structure

```
cli/
├── main.py                   # Entry point
├── parser.py                 # Argument parsing setup
├── autoloader.py             # Dynamic command/handler loading
├── exceptions/
│   └── cli_exceptions.py     # Custom exception classes
├── handlers/
│   ├── compile.py            # Compile handler (processes templates)
│   ├── build.py              # Build handler (creates images)
│   └── ...                   # Other handlers
├── commands/
│   ├── manifest.py           # Manifest command
│   ├── aipcc.py              # AIPCC command
│   ├── quay.py               # Quay registry command
│   └── ...                   # Other commands
└── jinja2/
    ├── environments.py       # Jinja2 setup
    └── extensions.py         # Custom Jinja2 filters/tags
```

## Core Components

### main.py - Entry Point

```python
def main():
    parser = create_parser()
    autoloader = CommandAutoloader()
    
    args = parser.parse_args()
    
    command = autoloader.get_command(args.command)
    command.execute(args)
```

Responsibilities:
- Parse command-line arguments
- Load the appropriate command/handler
- Execute with parsed arguments
- Handle exceptions gracefully

### parser.py - Argument Parsing

Uses `argparse` to define the CLI structure. Sets up:
- Main command parser
- Subparsers for each command
- Arguments and options for each command

```python
def create_parser():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')
    
    # Each command adds itself
    compile_parser = subparsers.add_parser('compile')
    compile_parser.add_argument('workbench')
    compile_parser.add_argument('--output', default='output')
    
    return parser
```

Pattern:
- Commands are registered as subparsers
- Arguments define what each command accepts
- Parser is flexible and extensible

### autoloader.py - Dynamic Loading

Automatically discovers and loads commands/handlers without hardcoding class names.

```python
class CommandAutoloader:
    def __init__(self, commands_dir='cli/commands', 
                 handlers_dir='cli/handlers'):
        self.commands = self._load_from_directory(commands_dir)
        self.handlers = self._load_from_directory(handlers_dir)
    
    def _load_from_directory(self, directory):
        # Scan directory for Python files
        # Import each module
        # Extract classes matching pattern
        # Return dictionary of name -> class
    
    def get_command(self, name):
        # Look in commands, then handlers
        # Return instance of the class
        # Raise error if not found
```

Key benefits:
- Add a new command just by creating a file
- No registration code needed
- Automatic discovery at runtime

### Handlers vs Commands

Both execute work, but serve different purposes:

**Handlers** - Primary operations (actions that modify state)
- `CompileHandler` - Generates files from templates
- `BuildHandler` - Creates container images
- `PushHandler` - Pushes images to registry

**Commands** - Secondary operations (queries, utilities)
- `ManifestCommand` - View/validate manifest files
- `ListCommand` - List available workbenches
- `AipccCommand` - AIPCC registry operations
- `QuayCommand` - Quay.io operations

Both follow the same interface:

```python
class MyHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def execute(self, args):
        """Main entry point. Called with parsed arguments."""
        # Do work
        return result
```

## Adding New Commands/Handlers

### Add a Simple Command

Create `cli/commands/mycommand.py`:

```python
import logging

class MycommandCommand:
    """Description of what this command does."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def execute(self, args):
        """Execute the command.
        
        Args:
            args: Parsed command-line arguments
        
        Returns:
            int: Exit code (0 for success)
        """
        self.logger.info("Running mycommand")
        
        # Access arguments
        value = args.my_argument
        
        # Do work
        result = self._do_something(value)
        
        # Log and return
        self.logger.info(f"Result: {result}")
        return 0
    
    def _do_something(self, value):
        """Helper method for the command logic."""
        return value.upper()
```

That's it. The autoloader finds it automatically, and users can run:

```bash
nb mycommand <arguments>
```

### Add a Handler with Logging

Create `cli/handlers/myhandler.py`:

```python
import logging
from pathlib import Path
from cli.exceptions import CLIException

class MyhandlerHandler:
    """Handler for expensive operations."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.workbench_root = Path('components/odh/workbenches')
    
    def execute(self, args):
        """Execute handler with error handling."""
        try:
            self.logger.info(f"Starting operation on {args.workbench}")
            
            # Validate input
            if not self._validate_workbench(args.workbench):
                raise CLIException(f"Workbench not found: {args.workbench}")
            
            # Do main work
            result = self._process(args)
            
            self.logger.info("Operation completed successfully")
            return 0
            
        except CLIException as e:
            self.logger.error(f"Operation failed: {e}")
            return 1
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}", exc_info=True)
            return 2
    
    def _validate_workbench(self, name):
        path = self.workbench_root / name
        return path.exists() and (path / 'manifest.toml').exists()
    
    def _process(self, args):
        # Main handler logic
        pass
```

Benefits of this pattern:
- Consistent error handling
- Structured logging
- Clear separation of concerns
- Easy to test

## Working with Manifests

### Reading a Manifest

```python
import tomllib
from pathlib import Path

class ManifestReader:
    def read(self, workbench_name):
        path = Path('components/odh/workbenches') / workbench_name / 'manifest.toml'
        
        with open(path, 'rb') as f:
            return tomllib.load(f)

# Usage
reader = ManifestReader()
manifest = reader.read('jupyter-minimal-cpu-py312-ubi9')

print(manifest['image']['name'])          # Access nested values
print(manifest['build']['platforms'])     # Lists, dicts work normally
```

### Validating Manifest

```python
def validate_manifest(manifest):
    """Ensure manifest has required sections."""
    required_sections = ['image', 'build']
    
    for section in required_sections:
        if section not in manifest:
            raise CLIException(f"Missing required section: {section}")
    
    # Validate specific fields
    if 'name' not in manifest['image']:
        raise CLIException("Missing 'image.name' in manifest")
    
    return True
```

## Working with Templates

### Rendering a Template

The `jinja2/environments.py` module sets up Jinja2:

```python
from cli.jinja2.environments import create_environment

env = create_environment()

# Load template
template = env.get_template('Dockerfile.j2', 
                           globals=manifest_data)

# Render with context
output = template.render(**manifest_data)

# Write result
Path('output/Dockerfile').write_text(output)
```

### Creating Custom Jinja2 Filters

Add to `cli/jinja2/extensions.py`:

```python
def uppercase_filter(value):
    """Convert string to uppercase."""
    return str(value).upper()

def custom_filter(value, separator='-'):
    """Custom filter with parameters."""
    return separator.join(str(value).split())
```

Register in `create_environment()`:

```python
def create_environment():
    env = Environment(loader=FileSystemLoader(...))
    
    # Register filters
    env.filters['uppercase'] = uppercase_filter
    env.filters['custom'] = custom_filter
    
    return env
```

Use in templates:

```jinja2
{{ workbench_name | uppercase }}
{{ python_packages | custom(separator='|') }}
```

## Error Handling

Create custom exceptions in `cli/exceptions/cli_exceptions.py`:

```python
class CLIException(Exception):
    """Base exception for CLI errors."""
    pass

class WorkbenchNotFound(CLIException):
    """Raised when workbench directory doesn't exist."""
    pass

class TemplateRenderError(CLIException):
    """Raised when template rendering fails."""
    pass

class ManifestError(CLIException):
    """Raised when manifest is invalid."""
    pass
```

Use in handlers:

```python
try:
    manifest = read_manifest(workbench_name)
except FileNotFoundError:
    raise WorkbenchNotFound(f"Workbench '{workbench_name}' not found")
except tomllib.TOMLDecodeError as e:
    raise ManifestError(f"Invalid manifest: {e}")
```

Handlers catch and log these:

```python
except CLIException as e:
    self.logger.error(str(e))
    return 1
```

## Testing Commands

Create tests in `tests/cli/commands/test_mycommand.py`:

```python
import pytest
from cli.commands.mycommand import MycommandCommand

class TestMycommandCommand:
    def setup_method(self):
        self.command = MycommandCommand()
    
    def test_execute_with_valid_input(self):
        class Args:
            my_argument = "test"
        
        result = self.command.execute(Args())
        assert result == 0
    
    def test_execute_with_invalid_input(self):
        class Args:
            my_argument = None
        
        result = self.command.execute(Args())
        assert result != 0
```

## Logging Best Practices

Use structured logging throughout:

```python
import logging

class MyHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def execute(self, args):
        # Info: notable events
        self.logger.info(f"Processing workbench: {args.workbench}")
        
        # Debug: detailed information
        self.logger.debug(f"Manifest: {manifest}")
        
        # Warning: something unexpected but not critical
        self.logger.warning(f"Slow operation took {duration}s")
        
        # Error: something failed
        self.logger.error(f"Failed to build image: {e}")
```

Enable debug output:

```bash
export NOTEBOOKS_DEBUG=1
nb compile jupyter-minimal-cpu-py312-ubi9
```

## Common Patterns

### Pattern 1: Find and Read

```python
def execute(self, args):
    workbench_path = self._find_workbench(args.workbench)
    manifest = self._read_manifest(workbench_path)
    return self._process(manifest)
```

### Pattern 2: Template and Write

```python
def execute(self, args):
    manifest = self._read_manifest(args.workbench)
    env = create_environment()
    
    for template_name in ['Dockerfile.j2', 'pyproject.toml.j2']:
        template = env.get_template(template_name, globals=manifest)
        output = template.render(**manifest)
        
        output_path = Path('output') / args.workbench / template_name[:-3]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
```

### Pattern 3: Validate and Process

```python
def execute(self, args):
    try:
        # Validate
        if not self._validate_input(args):
            raise CLIException("Invalid input")
        
        # Process
        result = self._process(args)
        
        # Confirm
        self.logger.info("Success")
        return 0
        
    except CLIException as e:
        self.logger.error(str(e))
        return 1
```

## Dependencies

Core dependencies (in `pyproject.toml`):

```toml
[dependency-groups]
cli = [
    "rich>=13.0.0",              # Terminal formatting
    "rich-argparse>=1.0.0",      # Pretty argument help
    "Jinja2>=3.0.0",             # Template rendering
]
```

Optional for extensions:
- `podman-py` - Programmatic Podman control
- `requests` - HTTP operations for Quay/registry
- `pydantic` - Data validation

## Extending the CLI

### Add a New Handler Type

1. Create file: `cli/handlers/newhandler.py`
2. Define class: `NewhandlerHandler`
3. Implement: `def execute(self, args)`
4. Autoloader finds it automatically

### Add Parser Arguments

Arguments are typically added in `parser.py`:

```python
compile_parser.add_argument(
    'workbench',
    help='Name of the workbench to compile'
)
compile_parser.add_argument(
    '--output',
    default='output',
    help='Output directory for generated files'
)
```

### Add Jinja2 Functionality

1. Custom filters: `cli/jinja2/extensions.py`
2. Custom tags: `cli/jinja2/extensions.py`
3. Register in: `cli/jinja2/environments.py`

### Add Exception Types

1. Create in: `cli/exceptions/cli_exceptions.py`
2. Inherit from: `CLIException`
3. Raise in handlers when appropriate

## Summary

The CLI is designed for:
- **Modularity** - Commands and handlers are independent
- **Extensibility** - Add new functionality without modifying existing code
- **Clarity** - Consistent patterns and structure
- **Robustness** - Error handling, logging, and validation

Follow the patterns shown above, and the CLI grows naturally as new features are needed.
