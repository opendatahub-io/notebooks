#!/usr/bin/env python3
import pathlib
import re
import yaml

import gen_gha_matrix_jobs
import gha_pr_changed_files

"""
This script is used to configure a Konflux Application with component definitions.
We have very many components, and clicking them one by one in the UI is too inefficient.

$ uv run ci/cached-builds/konflux_generate_component_definitions.py > konflux_components.yaml
$ oc apply -f konflux_components.yaml

Open https://console.redhat.com/application-pipeline/workspaces/rhoai-ide-konflux/applications
and see the result in the "Components" tab.
"""

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent

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
                # this annotation looks useful, but I don't know what it does
                # https://github.com/openshift-knative/hack/blob/a3a641238bab181b48e8cd8957f499402071d163/pkg/konfluxgen/dockerfile-component.template.yaml#L6
                # "build.appstudio.openshift.io/request": "configure-pac-no-mr",

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
            "build-nudges-ref": [ "manifests" ],
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
    images = gen_gha_matrix_jobs.extract_image_targets(makefile_dir=str(ROOT_DIR))
    for task in images:
        task_name = re.sub(r"[^-_0-9A-Za-z]", "-", task)
        dockerfile = gha_pr_changed_files.get_build_dockerfile(task)

        print("---")
        print(
            yaml.dump(
                konflux_component(task_name, dockerfile_path=dockerfile)
            )
        )


if __name__ == "__main__":
    main()
