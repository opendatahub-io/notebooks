from __future__ import annotations

import logging

import kubernetes
import kubernetes.dynamic.exceptions
import ocp_resources.deployment
import ocp_resources.resource


# https://github.com/RedHatQE/openshift-python-wrapper/tree/main/examples

def get_client() -> kubernetes.dynamic.DynamicClient:
    try:
        # client = kubernetes.dynamic.DynamicClient(client=kubernetes.config.new_client_from_config())
        # probably same as above
        client = ocp_resources.resource.get_client()
    except kubernetes.config.ConfigException as e:
        # probably bad config
        logging.error(e)
    except kubernetes.dynamic.exceptions.UnauthorizedError as e:
        # wrong or expired credentials
        logging.error(e)
    except kubernetes.client.ApiException as e:
        # unexpected, we catch unauthorized above
        logging.error(e)
    except Exception as e:
        # unexpected error, assert here
        logging.error(e)

    return client


def get_username(client: kubernetes.dynamic.DynamicClient) -> str:
    # can't just access
    # > client.configuration.username
    # because we normally auth using tokens, not username and password

    # this is what kubectl does (see kubectl -v8 auth whoami)
    self_subject_review_resource: kubernetes.dynamic.Resource = client.resources.get(
        api_version="authentication.k8s.io/v1", kind="SelfSubjectReview"
    )
    self_subject_review: kubernetes.dynamic.ResourceInstance = client.create(self_subject_review_resource)
    username: str = self_subject_review.status.userInfo.username
    return username


class TestKubernetesUtils:
    def test_get_username(self):
        client = get_client()
        username = get_username(client)
        assert username is not None and len(username) > 0


class TestFrame:
    def __init__(self):
        self.stack: list[ocp_resources.resource.Resource] = []

    def push(self, resource: ocp_resources.resource.Resource, wait=False):
        self.stack.append(resource)
        resource.deploy(wait=wait)

    def destroy(self, wait=False):
        while self.stack:
            resource = self.stack.pop()
            resource.clean_up(wait=wait)

    def __enter__(self) -> TestFrame:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.destroy()
