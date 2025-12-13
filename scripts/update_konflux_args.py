#!/usr/bin/env python3

from __future__ import annotations

import glob
import pathlib

from ntb import ROOT_DIR


def main() -> None:
    for filename in glob.glob("**/build-args/konflux.*.conf", root_dir=ROOT_DIR, recursive=True):
        filename = pathlib.Path(ROOT_DIR / filename)
        with open(filename, "r") as f:
            lines = f.readlines()

        match filename.name:
            case "konflux.cpu.conf":
                # https://catalog.redhat.com/en/software/containers/rhai/base-image-cpu-rhel9/690377f9d1c73dd1e81192f0?image=693be4e82524d9d966b3c9ef
                image = "registry.redhat.io/rhai/base-image-cpu-rhel9:3.2.0-1764872006"
            case "konflux.cuda.conf":
                # https://catalog.redhat.com/en/software/containers/rhai/base-image-cuda-rhel9/690377f9e1522d6afa972cc6?image=693be55d905e8cd3f800482e
                image = "registry.redhat.io/rhai/base-image-cuda-rhel9:3.2.0-1765367347"
            case "konflux.rocm.conf":
                # https://catalog.redhat.com/en/software/containers/rhai/base-image-rocm-rhel9/690377f9e1522d6afa972cc9?image=693be58457876b3b692e379e
                image = "registry.redhat.io/rhai/base-image-rocm-rhel9:3.2.0-1764877298"
            case _:
                raise ValueError(f"Unknown filename: {filename}")

        new_lines = []
        for line in lines:
            if line.startswith("BASE_IMAGE="):
                new_lines.append(f"BASE_IMAGE={image}\n")
            else:
                new_lines.append(line)

        if new_lines != lines:
            with open(filename, "wt") as f:
                f.writelines(new_lines)


if __name__ == "__main__":
    main()
