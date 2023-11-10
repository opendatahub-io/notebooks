ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.9" \
    summary="Jupyter CUDA tensorflow notebook image for ODH notebooks" \
    description="Jupyter CUDA tensorflow notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter CUDA tensorflow notebook image for ODH notebooks" \
    io.k8s.description="Jupyter CUDA tensorflow notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/tensorflow/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:cuda-jupyter-tensorflow-ubi9-python-3.9"

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
RUN sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json

# Disable announcement plugin of jupyterlab
RUN jupyter labextension disable "@jupyterlab/apputils-extension:announcements"

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P
