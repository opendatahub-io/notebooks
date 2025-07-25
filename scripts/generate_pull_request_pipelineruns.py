from __future__ import annotations

import io
import math
import pathlib
import textwrap
import unittest
from typing import Any, Literal

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

"""Generates -pull-request pipeline for every -push pipeline found in .tekton/"""

# --- Configuration ---
ROOT_DIR = pathlib.Path(__file__).parent.parent
TEKTON_DIR = ROOT_DIR / ".tekton"
PUSH_SUFFIX = "-push.yaml"
PR_SUFFIX = "-pull-request.yaml"


def main() -> int:
    """Main function to find and process all push pipelines."""
    tekton_path = pathlib.Path(TEKTON_DIR)
    if not tekton_path.is_dir():
        print(f"Error: Directory '{TEKTON_DIR}' not found.")
        return 1

    print(f"Searching for push pipelines in '{tekton_path}'...")

    push_pipelines = list(tekton_path.glob(f"*{PUSH_SUFFIX}"))

    if not push_pipelines:
        print("No push pipelines found.")
        return 1

    for pipeline_path in push_pipelines:
        print(f"\nFound push pipeline: {pipeline_path}")
        transform_build_pipeline_to_pr_pipeline(pipeline_path)

    print("\nScript finished.")
    return 0


def pull_request_pipelinerun_template(
        on_cel_expression: str,
        component: str,
        dockerfile: pathlib.Path,
        build_platforms: list[Literal['linux/x86_64', 'linux/arm64', 'linux/ppc64le', 'linux/s390x']]
) -> dict[str, Any]:
    return {
        'apiVersion': 'tekton.dev/v1',
        'kind': 'PipelineRun',
        'metadata': {
            'annotations': {
                'build.appstudio.openshift.io/repo': 'https://github.com/opendatahub-io/notebooks?rev={{revision}}',
                'build.appstudio.redhat.com/commit_sha': '{{revision}}',
                'build.appstudio.redhat.com/pull_request_number': '{{pull_request_number}}',
                'build.appstudio.redhat.com/target_branch': '{{target_branch}}',
                'pipelinesascode.tekton.dev/cancel-in-progress': 'true',
                'pipelinesascode.tekton.dev/max-keep-runs': '3',
                'pipelinesascode.tekton.dev/on-comment': f'^/kfbuild {dockerfile.parent}',
                'pipelinesascode.tekton.dev/on-cel-expression': on_cel_expression,
            },
            'labels': {
                'appstudio.openshift.io/application': 'opendatahub-release',
                'appstudio.openshift.io/component': component,
                'pipelines.appstudio.openshift.io/type': 'build',
            },
            'name': f'{component}-on-pull-request',
            'namespace': 'open-data-hub-tenant',
        },
        'spec': {
            'timeout': '4h0m0s',
            'params': [
                {
                    'name': 'git-url',
                    'value': '{{source_url}}'
                },
                {
                    'name': 'revision',
                    'value': '{{revision}}'
                },
                {
                    'name': 'output-image',
                    'value': f'quay.io/opendatahub/{component}:on-pr-{{{{revision}}}}'
                },
                {
                    'name': 'image-expires-after',
                    'value': '5d'
                },
                {
                    'name': 'build-platforms',
                    'value': build_platforms,
                },
                {
                    'name': 'dockerfile',
                    'value': str(dockerfile)
                },
                {
                    'name': 'path-context',
                    'value': '.',
                },
            ],
            'pipelineRef': {
                'name': 'multiarch-pull-request-pipeline',
            },
            'taskRunTemplate': {
                'serviceAccountName': f'build-pipeline-{component}',
            },
            'workspaces': [
                {
                    'name': 'git-auth',
                    'secret': {
                        'secretName': '{{ git_auth_secret }}',
                    },
                },
            ],
        },
        'status': {},
    }


def transform_build_pipeline_to_pr_pipeline(push_pipeline_path: pathlib.Path):
    """Reads a push pipeline YAML, transforms it into a pull-request pipeline,
    and writes it to a new file.
    """
    yaml = YAML()
    yaml.width = math.inf
    yaml.explicit_start = True

    with open(push_pipeline_path, 'r') as f:
        push_pipeline = yaml.load(f)
        f.seek(0)
        push_pipeline_lines = f.readlines()

    print(f"  - Processing '{push_pipeline['metadata']['name']}'")

    # Modify on-cel-expression
    annotations = push_pipeline['metadata']['annotations']
    cel_key = 'pipelinesascode.tekton.dev/on-cel-expression'
    original_on_cel_expression = get_exact_formatted_value(push_pipeline_lines, annotations.lc.key(cel_key),
                                                           annotations.lc.value(cel_key))

    pr_on_cel_expression = (original_on_cel_expression
                            .replace('"push"', '"pull_request"')
                            .replace('-push.yaml"', '-pull-request.yaml"')
                            + '&& body.repository.full_name == "opendatahub-io/notebooks"')

    component = push_pipeline['metadata']['labels']['appstudio.openshift.io/component']

    build_platforms = ['linux/x86_64']
    if component in [
        'odh-pipeline-runtime-minimal-cpu-py311-ubi9',
        'odh-pipeline-runtime-minimal-cpu-py312-ubi9'
    ]:
        build_platforms.append('linux/arm64')

    if component in [
        'odh-pipeline-runtime-minimal-cpu-py311-ubi9',
        'odh-pipeline-runtime-minimal-cpu-py312-ubi9'
    ]:
        build_platforms.append('linux/s390x')

    pr_pipeline = pull_request_pipelinerun_template(
        on_cel_expression=LiteralScalarString(pr_on_cel_expression + '\n'),
        component=component,
        dockerfile=pathlib.Path(next(param for param in push_pipeline['spec']['params']
                                     if param['name'] == 'dockerfile')['value']),
        build_platforms=build_platforms,
    )

    # Generate the new filename and write the file
    pr_pipeline_path = pathlib.Path(str(push_pipeline_path).replace(PUSH_SUFFIX, PR_SUFFIX))

    try:
        with open(pr_pipeline_path, 'w') as f:
            print(f"# yamllint disable-file", file=f)
            print(f"# This pipeline is autogenerated by {pathlib.Path(__file__).relative_to(ROOT_DIR)}", file=f)
            yaml.dump(pr_pipeline, f)
        print(f"  - Successfully generated: {pr_pipeline_path}")
    except Exception as e:
        print(f"  - Error writing new file: {e}")


def get_exact_formatted_value(lines: list[str], key: list[int], val: list[int]):
    """
    Finds a key in a YAML file and returns its value with the exact original
    multi-line formatting as it appears in the source file.
    """
    # Start with the first line of the value
    value_block_lines = [lines[val[0]][val[1]:]]

    # Add any additional lines that are part of the multi-line value
    for line_index in range(val[0] + 1, len(lines)):
        indent = len(lines[line_index]) - len(lines[line_index].lstrip())
        if indent <= key[1]:
            break
        value_block_lines.append(lines[line_index][key[1]:])

    # Join the lines back together, the original input already has newlines
    return value_block_lines[0] + textwrap.dedent("".join(value_block_lines[1:]))


if __name__ == "__main__":
    main()


class TestRaw(unittest.TestCase):
    def test_get_exact_formatted_value(self):
        """Demonstrates my best attempt at round-tripping a multi-line value.

        This is needed for handling on-cel-expression to avoid YAML
        parser munging the value into a single line string.
        """
        file = textwrap.dedent(
            """
            on-cel-expression: lek
              && mek
              || ook
            """
        ).lstrip()

        data = YAML().load(file)
        lines = file.splitlines(keepends=True)
        value = get_exact_formatted_value(lines, data.lc.key('on-cel-expression'), data.lc.value('on-cel-expression'))

        out = io.StringIO()
        YAML().dump({'on-cel-expression': LiteralScalarString(value)}, out)
        self.assertEqual(textwrap.dedent(
            """
            on-cel-expression: |
              lek
              && mek
              || ook
            """
        ).lstrip(), out.getvalue())
