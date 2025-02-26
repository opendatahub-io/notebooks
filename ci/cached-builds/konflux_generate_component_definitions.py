#!/usr/bin/env python3

import re
import yaml

import gen_gha_matrix_jobs
import gha_pr_changed_files

"""
This script is used to configure a Konflux Application with component definitions.
We have very many components, and clicking them one by one in the UI is too inefficient.

$ poetry run ci/cached-builds/konflux_generate_component_definitions.py > konflux_components.yaml
$ oc apply -f konflux_components.yaml

Open https://console.redhat.com/application-pipeline/workspaces/rhoai-ide-konflux/applications
and see the result in the "Components" tab.
"""

workspace_name = "rhoai-ide-konflux-tenant"
application_name = "notebooks"
application_uid = "eb0420e2-5bf3-42ef-848d-cc85c265b7dd"
git_revision = "main"
git_url = "https://github.com/opendatahub-io/notebooks"


def konflux_component(component_name, dockerfile_path) -> dict:
    return {
        "apiVersion": "appstudio.redhat.com/v1alpha1",
        "kind": "Component",
        "metadata": {
            "annotations": {
                # this annotation will create imagerepository in quay,
                # https://redhat-internal.slack.com/archives/C07S8637ELR/p1736436093726049?thread_ts=1736420157.217379&cid=C07S8637ELR
                "image.redhat.com/generate": '{"visibility": "public"}',

                "build.appstudio.openshift.io/status": '{"pac":{"state":"enabled","merge-url":"https://github.com/opendatahub-io/notebooks/pull/903","configuration-time":"Tue, 18 Feb 2025 12:39:27 UTC"},"message":"done"}',
                "build.appstudio.openshift.io/pipeline": '{"name":"docker-build-oci-ta","bundle":"latest"}',
                "git-provider": "github",
                "git-provider-url": "https://github.com",
            },
            "name": component_name,
            "namespace": workspace_name,
            "ownerReferences": [
                {
                    "apiVersion": "appstudio.redhat.com/v1alpha1",
                    "kind": "Application",
                    "name": application_name,
                    "uid": application_uid,
                }
            ],
            "finalizers": [
                "test.appstudio.openshift.io/component",
                "pac.component.appstudio.openshift.io/finalizer",
            ],
        },
        "spec": {
            "application": application_name,
            "componentName": component_name,
            "containerImage": "quay.io/redhat-user-workloads/"
                              + workspace_name
                              + "/"
                              + component_name,
            "resources": {},
            "source": {
                "git": {
                    "dockerfileUrl": dockerfile_path,
                    "revision": git_revision,
                    "url": git_url,
                }
            },
        },
    }


def main():
    with open("Makefile", "rt") as makefile:
        lines = gen_gha_matrix_jobs.read_makefile_lines(makefile)
    tree: dict[str, list[str]] = gen_gha_matrix_jobs.extract_target_dependencies(lines)

    for task, deps in tree.items():
        # in level 0, we only want base images, not other utility tasks
        if not deps:
            if not task.startswith("base-"):
                continue

        # we won't build rhel-based images because they need a subscription
        if "rhel" in task:
            continue

        task_name = re.sub(r"[^-_0-9A-Za-z]", "-", task)
        dirs = gha_pr_changed_files.analyze_build_directories(task)

        print("---")
        print(
            yaml.dump(
                konflux_component(task_name, dockerfile_path=dirs[-1] + "/Dockerfile")
            )
        )


if __name__ == "__main__":
    main()
