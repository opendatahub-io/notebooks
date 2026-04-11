# AI Agents Guide for OpenDataHub Notebooks

This document provides comprehensive instructions for AI agents working with the OpenDataHub Notebooks repository. It outlines the project structure, development workflows, and best practices for contributing to this containerized notebook environment project.

## Project Overview

The OpenDataHub Notebooks repository provides a collection of containerized notebook environments tailored for data analysis, machine learning, research, and coding within the OpenDataHub ecosystem. The project includes:

- **Jupyter Notebooks**: Various flavors (minimal, datascience, pytorch, tensorflow, trustyai)
- **Code Server**: VS Code-based development environments
- **RStudio**: R development environments
- **Runtime Images**: For pipeline execution with Elyra
- **Base Images**: CUDA and ROCm GPU-accelerated base images

## Repository Structure

### Key Directories

```
.
├── .github/ # GitHub-specific configuration (workflows, issue templates, etc.)
├── jupyter/ # Jupyter Notebook image definitions, organized by flavor and accelerator
│ ├── datascience/
│ ├── minimal/
│ ├── pytorch/
│ ├── pytorch+llmcompressor/
│ ├── rocm/
│ │ ├── pytorch/
│ │ └── tensorflow/
│ ├── tensorflow/
│ ├── trustyai/
├── runtimes/ # container images that Elyra plugin uses to execute pipeline nodes
│ ├── datascience/
│ ├── minimal/
│ ├── pytorch/
│ ├── pytorch+llmcompressor/
│ ├── rocm-pytorch/
│ ├── rocm-tensorflow/
│ └── tensorflow/
├── codeserver/ # Code-Server (VS Code in the browser) image definitions and configs
│ ├── ubi9-python-3.11/
├── rstudio/ # RStudio image definitions and configs
│ ├── rhel9-python-3.11/
│ └── c9s-python-3.11/
├── ci/ # Continuous Integration scripts, checks, and configuration
├── cuda/ # CUDA-specific files (NVIDIA GPU support), e.g., repo files, licenses
├── manifests/ # Kubernetes manifests for deploying the images
│ ├── odh/base/ # ODH (OpenDataHub) imagestream manifests — used when KONFLUX=no
│ └── rhoai/base/ # RHOAI (Red Hat AI) imagestream manifests — used when KONFLUX=yes
├── scripts/
├── tests/
├── README.md
├── Makefile # Build orchestration tool for local development
└── …
```

## Development Workflow

### Prerequisites

When working with this project, ensure these tools are available:
- **Container Runtime**: podman/docker
- **Python**: 3.14 (required)
- **Package Manager**: uv (preferred) or pipenv
- **Build System**: make (gmake on macOS)
- **Version Control**: git with proper signing
- **pinact**: for GitHub Actions SHA pinning (`brew install pinact`)

> **GitHub Actions changes:** See [`.github/AGENTS.md`](.github/AGENTS.md) for SHA pinning
> requirements, tooling, and workflow.

### Build Process

The project uses a Makefile-based build system:

```bash
# Build a specific workbench
make ${WORKBENCH_NAME} -e IMAGE_REGISTRY=quay.io/${YOUR_USER}/workbench-images -e RELEASE=2023x

# Example builds
make jupyter-minimal-ubi9-python-3.12
make jupyter-datascience-ubi9-python-3.12
make jupyter-pytorch-cuda-ubi9-python-3.12
```

#### ODH vs Konflux (RHOAI) builds

The `KONFLUX` Makefile variable (default: `no`) switches between two build variants:

- `KONFLUX=no` — builds from `Dockerfile.*`, uses `manifests/odh/base/` imagestream manifests
- `KONFLUX=yes` — builds from `Dockerfile.konflux.*`, uses `manifests/rhoai/base/` imagestream manifests

This variable must be set consistently across the build step **and** the test step (`make test-*`), as the test script (`scripts/test_jupyter_with_papermill.sh`) reads the imagestream manifest to derive expected package versions.
The Python equivalent (`tests/manifests.py::get_source_of_truth_filepath`) accepts a `konflux: bool` keyword argument for the same purpose.

### Testing Framework

The project uses pytest with testcontainers for container testing:

```bash
# Setup environment
./uv venv --python $(which python3.14)
./uv sync --locked

# Run tests
make test              # Quick static tests (pytest + Dockerfile alignment)
make test-unit         # Python unit tests + doctests + Go tests (no container runtime)
make test-integration PYTEST_ARGS="--image=<image>"  # Container integration tests
make test-${NOTEBOOK_NAME} # Specific notebook tests
```

## Agent Instructions

### General Guidelines

- Avoid unnecessary complexity: Aim for the simplest solution that works, while keeping the code clean.
- Avoid obvious comments: Only add comments to explain especially complex code blocks.
- Maintain code consistency: Follow existing code patterns and architecture.
- Maintain locality of behavior: Keep code close to where it's used.
- Make small, focused changes, unless explicitly asked otherwise.
- Keep security in mind: Avoid filtering sensitive information and running destructive commands.
- When in doubt about something, ask the user.

### When Working with This Repository

1. **Understand the Inheritance Model**: Notebook images inherit from parent images in a hierarchical structure:
   - Minimal → DataScience → Specialized (PyTorch, TensorFlow, TrustyAI)
   - Always check parent dependencies before adding new packages

2. **Package Management**:
   - Use `pyproject.toml` and `pylock.toml` for Python dependencies
   - Always regenerate lock files after dependency changes by running `make refresh-lock-files`

3. **Testing**:
   - Run `make test` and analyze logs

#### Modifying Existing Images

1. **Check Dependencies**:
   - Review parent image changes
   - Test downstream images
   - Update version compatibility files

2. **Security Updates**:
   - Scan for vulnerabilities using `ci/security-scan/`
   - Test with security scanning tools

### Code Quality Standards

1. **Python Code**:
   - Follow PEP 8 style guidelines
   - Use type hints where appropriate
   - Run `ruff` for linting
   - Use `pyright` for type checking
   - This project requires Python 3.14. PEP 758 allows `except ExcA, ExcB:` without
     parentheses to catch multiple exception types. This is NOT the old Python 2 syntax
     for `except ExcA as ExcB`. Parentheses are still required when binding with `as`:
     use `except (ExcA, ExcB) as e:`, not `except ExcA, ExcB as e:`. Ruff format
     enforces the parenthesis-free style when there is no `as` clause.

2. **Dockerfiles**:
   - Minimize layers
   - Follow security best practices

3. **Documentation**:
   - Update README files for new features
   - Add inline comments for complex logic
   - Update this Agents.md file for new patterns

### Testing Guidelines

1. **Unit Tests** (`tests/unit/`): Self-tests for scripts, CI utilities, and shared code.
   Mirror the source layout (e.g., `scripts/cve/` → `tests/unit/scripts/cve/`).
   Run with: `./uv run pytest tests/unit/`
2. **Static Tests** (`tests/*.py`): Use pytest to test config and manifests for consistency
3. **Container Tests** (`tests/containers/`): Use testcontainers for integration testing
4. **Browser Tests** (`tests/browser/`): Use Playwright for UI testing
5. **Manual Tests** (`tests/manual/`): Document manual testing procedures

### CI/CD Integration

The project uses GitHub Actions for:
- Automated testing
- Security scanning
- Dependency updates
- Image building and publishing

Key CI files:
- `.github/workflows/` - GitHub Actions workflows
- `ci/` - Custom CI scripts and configurations
- `scripts/ci/renovate_run.py` - Self-hosted Renovate (Podman or Docker via `CONTAINER_ENGINE`, same detection order as the Makefile); see `.github/workflows/renovate-self-hosted.yaml` and ADR 0013

### Deployment

1. **Local Development**:
```bash
podman run -it -p 8888:8888 quay.io/opendatahub/workbench-images:jupyter-minimal-ubi9-python-3.12-latest
```

2. **Kubernetes/OpenShift**:
```bash
make deploy9-${NOTEBOOK_NAME} # Deploy
make test-${NOTEBOOK_NAME} # Test
make undeploy9-${NOTEBOOK_NAME} # Cleanup
```

## Troubleshooting

### Common Issues

1. **Build Failures**:
   - Verify dependency versions
   - Review Dockerfile syntax

2. **Test Failures**:
   - Ensure container runtime is running
   - Check test environment setup
   - Review test logs for specific errors

3. **Dependency Conflicts**:
   - Use `uv` for dependency resolution
   - Check version compatibility files
   - Test with minimal dependencies first

### Getting Help

1. **Documentation**: Check `docs/` directory for detailed guides
2. **Issues**: Report issues on GitHub with detailed reproduction steps
3. **Community**: Engage with OpenDataHub community for support

## Best Practices Summary

1. **Always test changes** in isolated environments before committing
2. **Follow the inheritance model** when adding dependencies
3. **Update documentation** alongside code changes
4. **Use semantic versioning** for releases
5. **Maintain backward compatibility** when possible
6. **Security first** - scan images and update dependencies regularly
7. **Performance optimization** - use multi-stage builds and minimal base images

## Contributing

When contributing to this project:

1. **Fork and branch** from main
2. **Write clear commit messages**
3. **Add tests** for new functionality
4. **Update documentation**

For detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

*This document should be updated as the project evolves. AI agents working with this repository should refer to this guide for consistent and effective contributions.*
