#! /usr/bin/env python3
import os
import pathlib
import sys

def main():
    arg0 = pathlib.Path(sys.argv[0]).name
    args = []
    for arg in sys.argv[1:]:
        if arg.startswith("-Wp,-D"):
            args.append(arg.replace("-Wp,-D", "-D", 1))
        else:
            args.append(arg)

    if arg0 == "zig-cc":
        args = ["/mnt/zig", "cc", "-target", "s390x-linux-gnu.2.34"] + args
    elif arg0 == "zig-c++":
        args = ["/mnt/zig", "c++", "-target", "s390x-linux-gnu.2.34"] + args
    else:
        raise ValueError(f"Unknown argument {arg0}")

    os.execve(args[0], args, os.environ)

if __name__ == "__main__":
    sys.exit(main())
