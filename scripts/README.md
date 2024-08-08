# Scripts

## update_library_version.sh

This script updates the version of a specified library in Pipfile and requirements-elyra.txt files, only if the new version is higher. It can optionally run `pipenv lock` after updating the version.

### Examples

Update the `numpy` library to version `2.0.1` in all files under `./myproject`, and run `pipenv lock`:

```sh
./update_library_version.sh ./myproject numpy 2.0.1 '' '' true
```

Update the `pandas` library to version `2.2.2` in all files under `./myproject` where the directory contains `include` or `this`, excluding directories containing `exclude` or `that`, and do not run `pipenv lock`:

```sh
./update_library_version.sh ./myproject pandas 2.2.2 'include|this' 'exclude|that' false
```

