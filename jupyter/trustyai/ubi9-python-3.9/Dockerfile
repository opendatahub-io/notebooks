ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-trustyai-ubi9-python-3.9" \
    summary="Jupyter trustyai notebook image for ODH notebooks" \
    description="Jupyter trustyai notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter trustyai notebook image for ODH notebooks" \
    io.k8s.description="Jupyter trustyai notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/trustyai/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:jupyter-trustyai-ubi9-python-3.9"

USER 0

# Install jre that is needed to run the trustyai library
RUN INSTALL_PKGS="java-17-openjdk" && \
    yum install -y --setopt=tsflags=nodocs $INSTALL_PKGS && \
    yum -y clean all --enablerepo='*'

USER 1001

# Install Python packages and Jupyterlab extensions from pyproject.toml and poetry.lock
COPY pyproject.toml poetry.lock ./

RUN echo "Installing softwares and packages" && micropipenv install --method poetry && rm -f ./pyproject.toml ./poetry.lock && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y \
    sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P
