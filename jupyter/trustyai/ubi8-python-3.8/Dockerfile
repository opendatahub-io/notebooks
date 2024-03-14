ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG AUTHORITATIVE_SOURCE_URL
ARG BUILD_COMMIT_REF
ARG IMAGE_REGISTRY

LABEL name="odh-notebook-jupyter-trustyai-ubi8-python-3.8" \
    summary="Jupyter trustyai notebook image for ODH notebooks" \
    description="Jupyter trustyai notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    io.k8s.display-name="Jupyter trustyai notebook image for ODH notebooks" \
    io.k8s.description="Jupyter trustyai notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    authoritative-source-url="${AUTHORITATIVE_SOURCE_URL}" \
    io.openshift.build.commit.ref="${BUILD_COMMIT_REF}" \
    io.openshift.build.source-location="${AUTHORITATIVE_SOURCE_URL}/tree/${BUILD_COMMIT_REF}/jupyter/trustyai/ubi8-python-3.8" \
    io.openshift.build.image="${IMAGE_REGISTRY}:jupyter-trustyai-ubi8-python-3.8"

USER 0

# Install jre that is needed to run the trustyai library
RUN INSTALL_PKGS="java-17-openjdk" && \
    yum install -y --setopt=tsflags=nodocs $INSTALL_PKGS && \
    yum -y clean all --enablerepo='*'

USER 1001

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
RUN sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.8/site-packages && \
    fix-permissions /opt/app-root -P
