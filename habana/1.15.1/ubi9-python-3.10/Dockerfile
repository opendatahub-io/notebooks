# Copyright (c) 2022 Habana Labs, Ltd.
#
# SPDX-License-Identifier: Apache-2.0

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root

## Label the image with details required by ODH
LABEL name="odh-notebook-habana-jupyter-1.15.1-ubi9-python-3.10" \
    summary="Jupyter HabanaAI 1.15.1 notebook image for ODH notebooks" \
    description="Jupyter HabanaAI 1.15.1 notebook image with base Python 3.10 builder image based on ubi9 for ODH notebooks" \
    io.k8s.display-name="Jupyter HabanaAI 1.15.1 notebook image for ODH notebooks" \
    io.k8s.description="Jupyter HabanaAI 1.15.1 notebook image with base Python 3.10 builder image based on ubi9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/habana/1.15.1/ubi9-python-3.10" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:habana-jupyter-1.15.1-ubi9-python-3.10"

WORKDIR /opt/app-root/bin

COPY utils utils/

COPY Pipfile.lock start-notebook.sh ./

# Install Python dependencies from Pipfile.lock file
RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# Disable announcement plugin of jupyterlab
RUN jupyter labextension disable "@jupyterlab/apputils-extension:announcements"

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.10/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src

# Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
RUN sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json

USER 1001

ENTRYPOINT ["start-notebook.sh"]

WORKDIR /opt/app-root/src