#!/usr/bin/env python

from __future__ import annotations

import dataclasses
import glob
import io
import json
import pathlib
import typing
import unittest

import yaml

import package_versions_selftestdata

"""Generates the workbench software listings for https://access.redhat.com/articles/rhoai-supported-configs 
using the Markdown variant described at https://access.redhat.com/articles/7056942"""

ROOT_DIR = pathlib.Path(__file__).parent.parent


@dataclasses.dataclass
class Manifest:
    _data: any

    @property
    def name(self) -> str:
        return self._data['metadata']['annotations']['opendatahub.io/notebook-image-name']

    @property
    def order(self) -> int:
        return int(self._data['metadata']['annotations']['opendatahub.io/notebook-image-order'])

    @property
    def tags(self) -> list[Tag]:
        return [Tag(tag) for tag in self._data['spec']['tags']]


@dataclasses.dataclass()
class Tag:
    _data: any

    @property
    def name(self) -> str:
        return self._data['name']

    @property
    def recommended(self) -> bool:
        if 'opendatahub.io/workbench-image-recommended' not in self._data['annotations']:
            return False
        return self._data['annotations']['opendatahub.io/workbench-image-recommended'] == 'true'

    @property
    def outdated(self) -> bool:
        if 'opendatahub.io/image-tag-outdated' not in self._data['annotations']:
            return False
        return self._data['annotations']['opendatahub.io/image-tag-outdated'] == 'true'

    @property
    def sw_general(self) -> list[typing.TypedDict("Software", {"name": str, "version": str})]:
        return json.loads(self._data['annotations']['opendatahub.io/notebook-software'])

    @property
    def sw_python(self) -> list[typing.TypedDict("Software", {"name": str, "version": str})]:
        return json.loads(self._data['annotations']['opendatahub.io/notebook-python-dependencies'])


def main():
    pathname = 'manifests/base/*.yaml'
    # pathname = 'manifests/overlays/additional/*.yaml'
    imagestreams: list[Manifest] = []
    for fn in glob.glob(pathname, root_dir=ROOT_DIR):
        # there may be more than one yaml document in a file (e.g. rstudio buildconfigs)
        with (open(ROOT_DIR / fn, 'rt') as fp):
            for data in yaml.safe_load_all(fp):
                if 'kind' not in data or data['kind'] != 'ImageStream':
                    continue
                if 'labels' not in data['metadata']:
                    continue
                if ('opendatahub.io/notebook-image' not in data['metadata']['labels'] or
                        data['metadata']['labels']['opendatahub.io/notebook-image'] != 'true'):
                    continue
                imagestream = Manifest(data)
                imagestreams.append(imagestream)

    print('Image name | Image version | Preinstalled packages')
    print('--------- | ---------')

    # for imagestream in sorted(imagestreams, key=lambda imagestream: imagestream.order):
    for imagestream in sorted(imagestreams, key=lambda imagestream: imagestream.name):
        name = imagestream.name

        prev_tag = None
        for tag in imagestream.tags:
            if tag.outdated:
                continue

            tag_name = tag.name
            recommended = tag.recommended

            sw_general = tag.sw_general
            sw_python = tag.sw_python

            software: list[str] = []
            for item in sw_general:
                sw_name: str
                sw_version: str
                sw_name, sw_version = item['name'], item['version']
                sw_version = sw_version.lstrip("v")
                software.append(f"{sw_name} {sw_version}")
            for item in sw_python:
                sw_name: str
                sw_version: str
                sw_name, sw_version = item['name'], item['version']
                sw_version = sw_version.lstrip("v")
                software.append(f"{sw_name}: {sw_version}")

            maybe_techpreview = "" if name not in ('code-server',) else " (Technology Preview)"
            maybe_recommended = "" if not recommended or len(imagestream.tags) == 1 else ' (Recommended)'
            if not prev_tag:
                print(f'{name}{maybe_techpreview} | {tag_name}{maybe_recommended} | {', '.join(software)}')
            else:
                print(f'| {tag_name}{maybe_recommended} | {', '.join(software)}')

            prev_tag = tag


class TestManifest(unittest.TestCase):
    _data = yaml.safe_load(io.StringIO(package_versions_selftestdata.imagestream))
    manifest = Manifest(_data)

    def test_name(self):
        assert self.manifest.name == "Minimal Python"

    def test_order(self):
        assert self.manifest.order == 1

    def test_tag_name(self):
        assert self.manifest.tags[0].name == "2024.2"

    def test_tag_recommended(self):
        assert self.manifest.tags[0].recommended is True

    def test_tag_sw_general(self):
        assert self.manifest.tags[0].sw_general == [{'name': 'Python', 'version': 'v3.11'}]

    def test_tag_sw_python(self):
        assert self.manifest.tags[0].sw_python == [{'name': 'JupyterLab', 'version': '4.2'}]


if __name__ == '__main__':
    main()
