# ODH Notebooks CLI

The ODH Notebooks CLI is a command-line tool that automatically generates Dockerfiles and Python project configurations for Open Data Hub notebook images. It uses templates and configuration files to create consistent, multi-architecture container images from reusable components.

## Quick Start

### Installation

```bash
# Install from the notebooks directory
pip install -e .

# Or with CLI dependencies
pip install -e ".[cli]"
```

### Basic Usage

Run the CLI with the default interactive menu:

```bash
nb
```

This displays the main menu with all available commands.

### Run a Specific Command

Skip the main menu and run a command directly:

```bash
nb compile jupyter-minimal-cpu-py312-ubi9
```

### Non-Interactive Mode

Use flags to run without interactive prompts:

```bash
nb --non-interactive
nb --dry-run
```

## Available Commands

### Build Operations

**compile** - Generate Dockerfiles and configuration files from templates
```bash
nb compile <workbench-name>
nb compile jupyter-minimal-cpu-py312-ubi9
```

**build** - Build container images
```bash
nb build <image-name>
```

**push** - Push built images to a registry
```bash
nb push <image-name>
```

### Information Commands

**manifest** - View or validate manifest files
```bash
nb manifest <workbench-name>
```

**list** - List available workbenches
```bash
nb list
```

**status** - Check build status and environment
```bash
nb status
```

### Registry Commands

**quay** - Interact with Quay.io registry
```bash
nb quay <operation>
```

**aipcc** - Work with AIPCC (AI Platform Container Config)
```bash
nb aipcc <operation>
```

## Understanding Workbenches

A workbench is a directory containing everything needed to define a notebook image. Each workbench represents a specific combination of base system, Python version, GPU support, and pre-installed packages.

### Workbench Structure

```
components/odh/workbenches/jupyter-minimal-cpu-py312-ubi9/
├── manifest.toml          # Configuration (name, platforms, settings)
├── Dockerfile.j2          # Dockerfile template with variables
└── pyproject.toml.j2      # Python dependencies template
```

### Naming Convention

Workbench names follow this pattern:
```
jupyter-<type>-<platform>-<python>-<base>

jupyter-minimal-cpu-py312-ubi9
├─ jupyter     = notebook type
├─ minimal     = size/scope (minimal, datascience, tensorflow)
├─ cpu         = hardware platform (cpu, cuda, rocm)
├─ py312       = Python version (py310, py311, py312)
└─ ubi9        = base image (ubi9, etc.)
```

## Configuration Files

### manifest.toml

Describes a workbench's properties and build settings:

```toml
[image]
name = "Jupyter | Minimal | CPU | Python 3.12"
description = "Minimal Jupyter notebook with Python 3.12"
notebook_type = "minimal"
python_version = "3.12"

[build]
base_image = "registry.access.redhat.com/ubi9/ubi:latest"
platforms = ["x86_64", "ppc64le", "s390x"]

[registry]
quay_namespace = "opendatahub"
push_on_build = false
```

### pyproject.toml.j2

Template for Python dependencies. Variables from the manifest are substituted during compilation:

```toml
[project]
name = "jupyter-notebook"
version = "{{ version }}"

dependencies = [
    "jupyter=={{ jupyter_version }}",
    {% if gpu_support %}
    "tensorflow-gpu",
    {% endif %}
]
```

## Template Variables

Templates use Jinja2 syntax. Common variables come from the manifest:

```
{{ workbench_name }}      # From folder name
{{ image_name }}          # From [image] name
{{ base_image }}          # From [build] base_image
{{ python_version }}      # From [image] python_version
{{ arch }}                # Target architecture
```

Templates also support logic:

```jinja2
{% if gpu_support %}
    # GPU-specific instructions
{% endif %}

{% for package in packages %}
    RUN pip install {{ package }}
{% endfor %}
```

## Workflow Examples

### Generate Files for a Workbench

```bash
nb compile jupyter-minimal-cpu-py312-ubi9
```

This:
1. Finds the workbench directory
2. Reads `manifest.toml` for configuration
3. Processes templates using manifest values
4. Writes generated files to `output/jupyter-minimal-cpu-py312-ubi9/`

### Build a Container Image

```bash
nb build jupyter-minimal-cpu-py312-ubi9
```

The build command:
1. Compiles templates (same as above)
2. Uses `buildah` or `docker` to build the image
3. Tags it with the configured registry and namespace
4. Optionally pushes to the registry

## Output Structure

Generated files are written to the `output/` directory:

```
output/
├── jupyter-minimal-cpu-py312-ubi9/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .build-info
├── jupyter-datascience-cuda-py312-ubi9/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .build-info
└── ...
```

## Adding New Workbenches

To create a new notebook image variant:

1. Create a directory under `components/odh/workbenches/`:
   ```bash
   mkdir components/odh/workbenches/jupyter-custom-cpu-py312-ubi9
   ```

2. Create `manifest.toml` with configuration

3. Create `Dockerfile.j2` template using variables from manifest

4. Create `pyproject.toml.j2` with Python dependencies

5. Test compilation:
   ```bash
   nb compile jupyter-custom-cpu-py312-ubi9
   ```

## Troubleshooting

### "Workbench not found"

The workbench directory doesn't exist or the name is incorrect. Verify:
- Directory exists in `components/odh/workbenches/`
- Name matches exactly (case-sensitive)
- `manifest.toml` is present

### "Invalid template syntax"

Jinja2 template has an error. Check:
- All variables are spelled correctly and available in manifest
- All `{% if %}` blocks have closing `{% endif %}`
- All `{% for %}` blocks have closing `{% endfor %}`

### "TOML parsing error"

The manifest or pyproject template has invalid TOML syntax:
- Verify bracket matching
- Check for trailing commas in arrays
- Ensure all strings are properly quoted

## Getting Help

Run the CLI help system:

```bash
nb help                          # Main help
nb help compile                  # Help for specific command
nb --help                        # Standard help output
```

## Environment Variables

Optional configuration via environment variables:

```bash
# Set default registry
export NOTEBOOKS_REGISTRY=quay.io

# Set default namespace
export NOTEBOOKS_NAMESPACE=opendatahub

# Set build tool (docker or buildah)
export NOTEBOOKS_BUILD_TOOL=buildah

# Enable verbose output
export NOTEBOOKS_DEBUG=1
```

## Requirements

- Python 3.12+
- Docker or Podman for building images
- TOML support (included in Python 3.11+)

## Project Structure

```
notebooks/
├── cli/                          # CLI implementation
├── components/odh/
│   └── workbenches/              # Workbench definitions
├── output/                       # Generated files (git-ignored)
└── README.md                     # This file
```
