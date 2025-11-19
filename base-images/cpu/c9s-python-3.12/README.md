# AIPCC-like Python 3.12 base image

## Generating the list of additional packages

```commandline
podman run --rm --pull=always quay.io/sclorg/python-312-c9s:c9s rpm -qa '*' | sort > /tmp/scl_packages.txt
podman run --rm --pull=always quay.io/aipcc/base-images/cpu:3.1 rpm -qa '*' | sort > /tmp/aipcc_packages.txt
```

```python
def get_packages_from_file(filename: str) -> set[str]:
    """Reads a file and returns a set of package names."""
    with open(filename, 'r') as f:
        # We strip the version info from the package names (e.g., 'bash-5.1.8-6.el9_1.x86_64')
        # to get just the package name ('bash').
        return {line.strip().rsplit('-', 2)[0] for line in f if line.strip()}

def main():
    """
    Compares package lists from two files and prints the difference,
    formatted for inclusion in a bash script.
    """
    scl_packages = get_packages_from_file('/tmp/scl_packages.txt')
    aipcc_packages = get_packages_from_file('/tmp/aipcc_packages.txt')

    # Find packages in scl but not in aipcc
    difference = sorted(list(scl_packages - aipcc_packages))

    # Format for bash array
    print("SCL_PACKAGES=(")
    for pkg in difference:
        print(f'    "{pkg}"')
    print(")")

if __name__ == "__main__":
    main()
```
