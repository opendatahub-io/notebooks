#########################################################################################
# SOF                                                                                   #
#########################################################################################

#########################################################################################
# Imports                                                                               #
#########################################################################################

import re
import requests
import argparse
from pathlib import Path
import sys

#########################################################################################
# Helper functions                                                                      #
#########################################################################################

def get_canonical_name(name):
    url = f"https://pypi.org/pypi/{name.lower()}/json"
    try:
        resp = requests.get(url, timeout=5)
        if resp.ok:
            pypi_name = resp.json()['info']['name']
            return re.sub(r"[-_.]+", "-", name).lower() 
    except Exception:
        pass
    return name 

def normalize_pipfile_packages(pipfile_path):
    with open(pipfile_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_packages = False
    in_dev_packages = False
    pkg_pattern = re.compile(r"^([a-zA-Z0-9_.-]+)\s*=")
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[packages]"):
            in_packages = True
            in_dev_packages = False
            new_lines.append(line)
            continue
        elif stripped.startswith("[dev-packages]"):
            in_packages = False
            in_dev_packages = True
            new_lines.append(line)
            continue
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_packages = False
            in_dev_packages = False
            new_lines.append(line)
            continue
        if in_packages or in_dev_packages:
            match = pkg_pattern.match(stripped)
            if match:
                orig_pkg = match.group(1)
                canonical = get_canonical_name(orig_pkg).lower()
                
                if canonical == orig_pkg:
                    print("\t[no-change] Original package name: "+orig_pkg+ "  ->  "+canonical)
                    new_line = line
                else:
                    print("\t[ changed ] Original package name: "+orig_pkg+ "  ->  "+canonical)
                    new_line = line.replace(orig_pkg, canonical, 1)            
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(pipfile_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

#########################################################################################
# MAIN                                                                                  #
#########################################################################################

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description="Updates package names in all Pipfiles found within a given directory and its subdirectories by querying PyPI for the canonical names.",
        usage="python fix_package_naming.py --context-dir <directory>")
    
    parser.add_argument("--context-dir", help="The directory to be the context for searching.")

    args = parser.parse_args()

    missing_args = [arg for arg, value in vars(args).items() if value is None]
    if missing_args:
        print(f"Missing required arguments: {', '.join(missing_args)}")
        parser.print_help()

    root_path = Path(args.context_dir).resolve()
    pipfiles = list(root_path.rglob("Pipfile"))
    if not pipfiles:
        print("No Pipfile found.")
        exit()
    
    for pf in pipfiles:
        print(f"Processing {pf}")
        normalize_pipfile_packages(pf)
        print(f"Updated {pf}")

#########################################################################################
# EOF                                                                                   #
#########################################################################################