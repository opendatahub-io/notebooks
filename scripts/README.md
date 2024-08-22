# Scripts

## update_library_version.sh

This script updates the version of one or more libraries in Pipfile and requirements-elyra.txt files, only if the new version is higher. It can optionally run `pipenv lock` after updating the version.

### Examples

Update the `numpy` library to version `2.0.1` and the `pandas` library to version `2.2.2` in all files under the current folder (`.`), and run `pipenv lock`:

```sh
./scripts/update_library_version.sh . '[{"name":"numpy","version":"2.0.1"},{"name":"pandas","version":"2.2.2"}]' '' '' true
```

Update the `pandas` library to version `2.2.2` in all files under the current folder (`.`), where the directory contains `include` or `this`, excluding directories containing `exclude` or `that`, and do not run `pipenv lock`:

```sh
./scripts/update_library_version.sh . '[{"name":"pandas","version":"2.2.2"}]' 'include|this' 'exclude|that' false
```

## new_python_based_image.py

This Python script generates a new folder structure for a Python-based project by copying an existing one and updating Python version references. It performs the following steps:

1. Copy Folder: Duplicates the specified folder structure.
1. Update Python Versions: Replaces occurrences of the source Python version with the target version throughout the folder.
1. Update Lock Files: Executes `pipenv lock` to regenerate lock files based on the new Python version.

If `pipenv lock` encounters errors, manual intervention is required to resolve compatibility issues between dependencies. Review the errors reported by `pipenv` and adjust the dependencies as needed.

### Examples

Create a Python 3.12 version based on the Python 3.9 version for each one that is in the `./base` directory:

```sh
python scripts/new_python_based_image.py --context-dir . --source 3.9 --target 3.12 --match ./base
```

Create a Python 3.11 version based on the Python 3.9 versions for each one that is in the `./jupyter/rocm` directory:

```sh
python scripts/new_python_based_image.py --context-dir . --source 3.9 --target 3.11 --match ./jupyter/rocm
```

Create a Python 3.11 version based on the Python 3.9 version for each one in the repository with `DEBUG` logs enabled:

```sh
python scripts/new_python_based_image.py --context-dir . --source 3.9 --target 3.11 --match ./ --log-level DEBUG
```
