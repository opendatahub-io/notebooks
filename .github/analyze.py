import glob
import pathlib
import subprocess

if __name__ == '__main__':
    first = None
    # pyrefly: ignore  # bad-assignment
    for line in glob.glob("**/partial-body.html", recursive=True):
        file = pathlib.Path(line)
        utils = file.parent.parent
        if first is None:
            first = utils
        else:
            print()
            subprocess.check_call(f"diff --recursive --no-dereference '{first}' '{utils}'", shell=True)
