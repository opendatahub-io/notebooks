ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-pytorch-ubi8-python-3.8" \
    summary="Jupyter pytorch notebook image for ODH notebooks" \
    description="Jupyter pytorch notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    io.k8s.display-name="Jupyter pytorch notebook image for ODH notebooks" \
    io.k8s.description="Jupyter pytorch notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/pytorch/ubi8-python-3.8" \
    io.openshift.build.image="quay.io/opendatahub/notebooks:jupyter-pytorch-ubi8-python-3.8"

# Install Python packages and Jupyterlab extensions from requirements.txt
COPY requirements.txt ./

RUN python -m pip install -r requirements.txt && \
    rm -f requirements.txt

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.8/site-packages && \
    fix-permissions /opt/app-root -P
