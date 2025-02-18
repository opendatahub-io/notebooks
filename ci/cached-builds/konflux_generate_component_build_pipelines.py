#!/usr/bin/env python3

import re
import pathlib
import yaml

import gen_gha_matrix_jobs
import gha_pr_changed_files

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent

workspace_name = "rhoai-ide-konflux-tenant"
application_name = "notebooks"
git_revision = "main"
git_url = "https://github.com/opendatahub-io/notebooks"

"""
We have great many components and their pipeline specs are very repetitive.

This script creates the Tekton pipelines under /.tekton

Usage:

$ poetry run ci/cached-builds/konflux_generate_component_build_pipelines.py
"""


def bundle_task_ref(name) -> dict:
    """Returns a reference to a Konflux task bundle.

    Uses the `image-registry.yaml` file as an up-to-date source for the digests."""
    with open(ROOT_DIR / ".tekton/image-registry.yaml") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
        images: list[str] = [image['spec']['taskRef']['bundle'] for image in data['items']]
        for image in images:
            if re.search(f'^quay.io/konflux-ci/tekton-catalog/task-{name}:', image):
                bundle = image
                break
        else:
            raise Exception(f"Could not find bundle {name}")

    return {
        "params": [
            {"name": "name", "value": name},
            {
                "name": "bundle",
                "value": bundle,
            },
            {"name": "kind", "value": "task"},
        ],
        "resolver": "bundles",
    }


def build_container(
        name_suffix: str = "",
        output_image: str = "$(params.output-image)",
        dockerfile: str = "$(params.dockerfile)",
        run_after: str = "prefetch-dependencies",
        build_arg: str = "$(params.build-args[*])") -> dict:
    """Returns a build-container step definition for the Konflux pipeline."""
    return {
        "name": "build-container" + name_suffix,
        "params": [
            {"name": "IMAGE", "value": output_image},
            {"name": "DOCKERFILE", "value": dockerfile},
            {"name": "CONTEXT", "value": "$(params.path-context)"},
            {"name": "HERMETIC", "value": "$(params.hermetic)"},
            {"name": "PREFETCH_INPUT", "value": "$(params.prefetch-input)"},
            {
                "name": "IMAGE_EXPIRES_AFTER",
                "value": "$(params.image-expires-after)",
            },
            {
                "name": "COMMIT_SHA",
                "value": "$(tasks.clone-repository.results.commit)",
            },
            {"name": "BUILD_ARGS", "value": [build_arg]},
            {
                "name": "BUILD_ARGS_FILE",
                "value": ["$(params.build-args-file)"],
            },
            {
                "name": "SOURCE_ARTIFACT",
                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
            },
            {
                "name": "CACHI2_ARTIFACT",
                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)",
            },
        ],
        "runAfter": [run_after],
        "taskRef": bundle_task_ref("buildah-remote-oci-ta"),
        "when": [
            {
                "input": "$(tasks.init.results.build)",
                "operator": "in",
                "values": ["true"],
            }
        ],
    }


def component_build_pipeline(component_name, dockerfile_path,
                             build_container_tasks: list[dict], is_pr: bool = True) -> dict:
    """Returns a component build pipeline definition.

    This is general enough to create PR pipeline as well as push pipeline.
    """
    name = component_name + ("-on-pull-request" if is_pr else "-on-push")
    return {
        "apiVersion": "tekton.dev/v1",
        "kind": "PipelineRun",
        "metadata": {
            "annotations": {
                "build.appstudio.openshift.io/repo": git_url + "?rev={{revision}}",
                "build.appstudio.redhat.com/commit_sha": "{{revision}}",
                **({"build.appstudio.redhat.com/pull_request_number": "{{pull_request_number}}"} if is_pr else {}),
                "build.appstudio.redhat.com/target_branch": "{{target_branch}}",
                "pipelinesascode.tekton.dev/cancel-in-progress": "true" if is_pr else "false",
                "pipelinesascode.tekton.dev/max-keep-runs": "3",
                "pipelinesascode.tekton.dev/on-cel-expression": (
                    f'event == "{"pull_request" if is_pr else "push"}" && target_branch == "main"'
                    + ' && has(body.repository) && body.repository.full_name == "opendatahub-io/notebooks"'
                ),
            },
            "creationTimestamp": None,
            "labels": {
                "appstudio.openshift.io/application": application_name,
                "appstudio.openshift.io/component": component_name,
                "pipelines.appstudio.openshift.io/type": "build",
            },
            "name": name,
            "namespace": workspace_name,
        },
        "spec": {
            "params": [
                {"name": "git-url", "value": "{{source_url}}"},
                {"name": "revision", "value": "{{revision}}"},
                {
                    "name": "output-image",
                    "value": "quay.io/redhat-user-workloads/" + workspace_name + "/" + component_name + ":" + (
                        "on-pr-" if is_pr else "") + "{{revision}}",
                },
                {"name": "image-expires-after", "value": "5d" if is_pr else "28d"},
                {"name": "build-platforms", "value": ["linux/x86_64"]},
                {"name": "dockerfile", "value": dockerfile_path},
            ],
            "pipelineSpec": {
                "description": "This pipeline is ideal for building multi-arch container images from a Containerfile while maintaining trust after pipeline customization.\n\n_Uses `buildah` to create a multi-platform container image leveraging [trusted artifacts](https://konflux-ci.dev/architecture/ADR/0036-trusted-artifacts.html). It also optionally creates a source image and runs some build-time tests. This pipeline requires that the [multi platform controller](https://github.com/konflux-ci/multi-platform-controller) is deployed and configured on your Konflux instance. Information is shared between tasks using OCI artifacts instead of PVCs. EC will pass the [`trusted_task.trusted`](https://enterprisecontract.dev/docs/ec-policies/release_policy.html#trusted_task__trusted) policy as long as all data used to build the artifact is generated from trusted tasks.\nThis pipeline is pushed as a Tekton bundle to [quay.io](https://quay.io/repository/konflux-ci/tekton-catalog/pipeline-docker-build-multi-platform-oci-ta?tab=tags)_\n",
                "finally": [
                    {
                        "name": "show-sbom",
                        "params": [
                            {
                                "name": "IMAGE_URL",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            }
                        ],
                        "taskRef": bundle_task_ref("show-sbom")
                    }
                ],
                "params": [
                    {
                        "description": "Source Repository URL",
                        "name": "git-url",
                        "type": "string",
                    },
                    {
                        "default": "",
                        "description": "Revision of the Source Repository",
                        "name": "revision",
                        "type": "string",
                    },
                    {
                        "description": "Fully Qualified Output Image",
                        "name": "output-image",
                        "type": "string",
                    },
                    {
                        "default": ".",
                        "description": "Path to the source code of an application's component from where to build image.",
                        "name": "path-context",
                        "type": "string",
                    },
                    {
                        "default": "Dockerfile",
                        "description": "Path to the Dockerfile inside the context specified by parameter path-context",
                        "name": "dockerfile",
                        "type": "string",
                    },
                    {
                        "default": "false",
                        "description": "Force rebuild image",
                        "name": "rebuild",
                        "type": "string",
                    },
                    {
                        "default": "false",
                        "description": "Skip checks against built image",
                        "name": "skip-checks",
                        "type": "string",
                    },
                    {
                        "default": "false",
                        "description": "Execute the build with network isolation",
                        "name": "hermetic",
                        "type": "string",
                    },
                    {
                        "default": "",
                        "description": "Build dependencies to be prefetched by Cachi2",
                        "name": "prefetch-input",
                        "type": "string",
                    },
                    {
                        "default": "",
                        "description": "Image tag expiration time, time values could be something like 1h, 2d, 3w for hours, days, and weeks, respectively.",
                        "name": "image-expires-after",
                    },
                    {
                        "default": "false",
                        "description": "Build a source image.",
                        "name": "build-source-image",
                        "type": "string",
                    },
                    {
                        "default": "true",
                        "description": "Add built image into an OCI image index",
                        "name": "build-image-index",
                        "type": "string",
                    },
                    {
                        "default": [],
                        "description": 'Array of --build-arg values ("arg=value" strings) for buildah',
                        "name": "build-args",
                        "type": "array",
                    },
                    {
                        "default": "",
                        "description": "Path to a file with build arguments for buildah, see https://www.mankier.com/1/buildah-build#--build-arg-file",
                        "name": "build-args-file",
                        "type": "string",
                    },
                    {
                        "default": ["linux/x86_64"],
                        "description": "List of platforms to build the container images on. The available set of values is determined by the configuration of the multi-platform-controller.",
                        "name": "build-platforms",
                        "type": "array",
                    },
                ],
                "results": [
                    {
                        "description": "",
                        "name": "IMAGE_URL",
                        "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                    },
                    {
                        "description": "",
                        "name": "IMAGE_DIGEST",
                        "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                    },
                    {
                        "description": "",
                        "name": "CHAINS-GIT_URL",
                        "value": "$(tasks.clone-repository.results.url)",
                    },
                    {
                        "description": "",
                        "name": "CHAINS-GIT_COMMIT",
                        "value": "$(tasks.clone-repository.results.commit)",
                    },
                ],
                "tasks": [
                    {
                        "name": "init",
                        "params": [
                            {"name": "image-url", "value": "$(params.output-image)"},
                            {"name": "rebuild", "value": "$(params.rebuild)"},
                            {"name": "skip-checks", "value": "$(params.skip-checks)"},
                        ],
                        "taskRef": bundle_task_ref("init"),
                    },
                    {
                        "name": "clone-repository",
                        "params": [
                            {"name": "url", "value": "$(params.git-url)"},
                            {"name": "revision", "value": "$(params.revision)"},
                            {"name": "ociStorage", "value": "$(params.output-image).git"},
                            {
                                "name": "ociArtifactExpiresAfter",
                                "value": "$(params.image-expires-after)",
                            },
                        ],
                        "runAfter": ["init"],
                        "taskRef": bundle_task_ref("git-clone-oci-ta"),
                        "when": [
                            {
                                "input": "$(tasks.init.results.build)",
                                "operator": "in",
                                "values": ["true"],
                            }
                        ],
                        "workspaces": [{"name": "basic-auth", "workspace": "git-auth"}],
                    },
                    {
                        "name": "prefetch-dependencies",
                        "params": [
                            {"name": "input", "value": "$(params.prefetch-input)"},
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.clone-repository.results.SOURCE_ARTIFACT)",
                            },
                            {
                                "name": "ociStorage",
                                "value": "$(params.output-image).prefetch",
                            },
                            {
                                "name": "ociArtifactExpiresAfter",
                                "value": "$(params.image-expires-after)",
                            },
                        ],
                        "runAfter": ["clone-repository"],
                        "taskRef": bundle_task_ref("prefetch-dependencies-oci-ta"),
                        "workspaces": [
                            {"name": "git-basic-auth", "workspace": "git-auth"},
                            {"name": "netrc", "workspace": "netrc"},
                        ],
                    },
                    {
                        "matrix": {
                            "params": [
                                {
                                    "name": "PLATFORM",
                                    "value": ["$(params.build-platforms)"]
                                }
                            ]
                        },
                        "name": "build-images",
                        "params": [
                            {
                                "name": "IMAGE",
                                "value": "$(params.output-image)"
                            },
                            {
                                "name": "DOCKERFILE",
                                "value": "$(params.dockerfile)"
                            },
                            {
                                "name": "CONTEXT",
                                "value": "$(params.path-context)"
                            },
                            {
                                "name": "HERMETIC",
                                "value": "$(params.hermetic)"
                            },
                            {
                                "name": "PREFETCH_INPUT",
                                "value": "$(params.prefetch-input)"
                            },
                            {
                                "name": "IMAGE_EXPIRES_AFTER",
                                "value": "$(params.image-expires-after)"
                            },
                            {
                                "name": "COMMIT_SHA",
                                "value": "$(tasks.clone-repository.results.commit)"
                            },
                            {
                                "name": "BUILD_ARGS",
                                "value": ["$(params.build-args[*])"]
                            },
                            {
                                "name": "BUILD_ARGS_FILE",
                                "value": "$(params.build-args-file)"
                            },
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)"
                            },
                            {
                                "name": "CACHI2_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)"
                            },
                            {
                                "name": "IMAGE_APPEND_PLATFORM",
                                "value": "true"
                            }
                        ],
                        "runAfter": ["prefetch-dependencies"],
                        "taskRef": bundle_task_ref("buildah-remote-oci-ta"),
                        "when": [
                            {
                                "input": "$(tasks.init.results.build)",
                                "operator": "in",
                                "values": ["true"]
                            }
                        ]
                    },
                    {
                        "name": "build-image-index",
                        "params": [
                            {"name": "IMAGE", "value": "$(params.output-image)"},
                            {
                                "name": "COMMIT_SHA",
                                "value": "$(tasks.clone-repository.results.commit)",
                            },
                            {
                                "name": "IMAGE_EXPIRES_AFTER",
                                "value": "$(params.image-expires-after)",
                            },
                            {
                                "name": "ALWAYS_BUILD_INDEX",
                                "value": "$(params.build-image-index)",
                            },
                            {
                                "name": "IMAGES",
                                "value": [
                                    "$(tasks.build-images.results.IMAGE_REF[*])"
                                ],
                            },
                        ],
                        "runAfter": ["build-images"],
                        "taskRef": bundle_task_ref("build-image-index"),
                        "when": [
                            {
                                "input": "$(tasks.init.results.build)",
                                "operator": "in",
                                "values": ["true"],
                            }
                        ],
                    },
                    {
                        "name": "build-source-image",
                        "params": [
                            {"name": "BINARY_IMAGE", "value": "$(params.output-image)"},
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
                            },
                            {
                                "name": "CACHI2_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("source-build-oci-ta"),
                        "when": [
                            {
                                "input": "$(tasks.init.results.build)",
                                "operator": "in",
                                "values": ["true"],
                            },
                            {
                                "input": "$(params.build-source-image)",
                                "operator": "in",
                                "values": ["true"],
                            },
                        ],
                    },
                    {
                        "name": "deprecated-base-image-check",
                        "params": [
                            {
                                "name": "IMAGE_URL",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "IMAGE_DIGEST",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("deprecated-image-check"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "clair-scan",
                        "params": [
                            {
                                "name": "image-digest",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("clair-scan"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "ecosystem-cert-preflight-checks",
                        "params": [
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            }
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("ecosystem-cert-preflight-checks"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "sast-snyk-check",
                        "params": [
                            {
                                "name": "image-digest",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
                            },
                            {
                                "name": "CACHI2_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("sast-snyk-check-oci-ta"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "clamav-scan",
                        "params": [
                            {
                                "name": "image-digest",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("clamav-scan"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "sast-coverity-check",
                        "params": [
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "IMAGE",
                                "value": "$(params.output-image)",
                            },
                            {
                                "name": "DOCKERFILE",
                                "value": "$(params.dockerfile)",
                            },
                            {
                                "name": "CONTEXT",
                                "value": "$(params.path-context)",
                            },
                            {
                                "name": "HERMETIC",
                                "value": "$(params.hermetic)",
                            },
                            {
                                "name": "PREFETCH_INPUT",
                                "value": "$(params.prefetch-input)",
                            },
                            {
                                "name": "IMAGE_EXPIRES_AFTER",
                                "value": "$(params.image-expires-after)",
                            },
                            {
                                "name": "COMMIT_SHA",
                                "value": "$(tasks.clone-repository.results.commit)",
                            },
                            {
                                "name": "BUILD_ARGS",
                                "value": ["$(params.build-args[*])"],
                            },
                            {
                                "name": "BUILD_ARGS_FILE",
                                "value": "$(params.build-args-file)",
                            },
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
                            },
                            {
                                "name": "CACHI2_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)",
                            },
                        ],
                        "runAfter": ["coverity-availability-check"],
                        "taskRef": bundle_task_ref("sast-coverity-check-oci-ta"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            },
                            {
                                "input": "$(tasks.coverity-availability-check.results.STATUS)",
                                "operator": "in",
                                "values": ["success"],
                            },
                        ],
                    },
                    {
                        "name": "coverity-availability-check",
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("coverity-availability-check"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "sast-shell-check",
                        "params": [
                            {
                                "name": "image-digest",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
                            },
                            {
                                "name": "CACHI2_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("sast-shell-check-oci-ta"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "sast-unicode-check",
                        "params": [
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
                            },
                            {
                                "name": "CACHI2_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.CACHI2_ARTIFACT)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("sast-unicode-check-oci-ta"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                    {
                        "name": "apply-tags",
                        "params": [
                            {
                                "name": "IMAGE",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            }
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("apply-tags"),
                    },
                    {
                        "name": "push-dockerfile",
                        "params": [
                            {
                                "name": "IMAGE",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "IMAGE_DIGEST",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                            {"name": "DOCKERFILE", "value": "$(params.dockerfile)"},
                            {"name": "CONTEXT", "value": "$(params.path-context)"},
                            {
                                "name": "SOURCE_ARTIFACT",
                                "value": "$(tasks.prefetch-dependencies.results.SOURCE_ARTIFACT)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("push-dockerfile-oci-ta"),
                    },
                    {
                        "name": "rpms-signature-scan",
                        "params": [
                            {
                                "name": "image-url",
                                "value": "$(tasks.build-image-index.results.IMAGE_URL)",
                            },
                            {
                                "name": "image-digest",
                                "value": "$(tasks.build-image-index.results.IMAGE_DIGEST)",
                            },
                        ],
                        "runAfter": ["build-image-index"],
                        "taskRef": bundle_task_ref("rpms-signature-scan"),
                        "when": [
                            {
                                "input": "$(params.skip-checks)",
                                "operator": "in",
                                "values": ["false"],
                            }
                        ],
                    },
                ],
                "workspaces": [
                    {"name": "git-auth", "optional": True},
                    {"name": "netrc", "optional": True},
                ],
            },
            "taskRunTemplate": {},
            "workspaces": [
                {"name": "git-auth", "secret": {"secretName": "{{ git_auth_secret }}"}}
            ],
        },
        "status": {},
    }


# https://stackoverflow.com/questions/20805418/pyyaml-dump-format
def represent_str(self, data):
    style = None
    if '{' in data or '}' in data:
        style = "'"
    if "\n" in data:
        style = '|'
    if data in ["true", "false", ""]:
        style = '"'
    return self.represent_scalar(u'tag:yaml.org,2002:str', data, style=style)


def main():
    yaml.add_representer(str, represent_str)

    images = gen_gha_matrix_jobs.extract_image_targets(makefile_dir=str(ROOT_DIR))
    for task in images:
        task_name = re.sub(r"[^-_0-9A-Za-z]", "-", task)
        dockerfile = gha_pr_changed_files.get_build_dockerfile(task)
        with open(ROOT_DIR / ".tekton" / (task_name + "-push.yaml"), "w") as yaml_file:
            print("# yamllint disable-file", file=yaml_file)
            print("# This file is autogenerated by ci/cached-builds/konflux_generate_component_build_pipelines.py",
                  file=yaml_file)
            print(yaml.dump(component_build_pipeline(component_name=task_name, dockerfile_path=dockerfile,
                                                     build_container_tasks=[build_container()], is_pr=False)),
                  end="",
                  file=yaml_file)
        with open(ROOT_DIR / ".tekton" / (task_name + "-pull-request.yaml"), "w") as yaml_file:
            print("# yamllint disable-file", file=yaml_file)
            print("# This file is autogenerated by ci/cached-builds/konflux_generate_component_build_pipelines.py",
                  file=yaml_file)
            print(yaml.dump(component_build_pipeline(component_name=task_name, dockerfile_path=dockerfile,
                                                     build_container_tasks=[build_container()], is_pr=True)),
                  end="",
                  file=yaml_file)


if __name__ == "__main__":
    main()
