ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG SOURCE_CODE=.

LABEL name="odh-notebook-jupyter-rocm-pytorch-ubi9-python-3.11" \
    summary="Jupyter AMD pytorch notebook image for ODH notebooks" \
    description="Jupyter AMD pytorch notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter AMD pytorch notebook image for ODH notebooks" \
    io.k8s.description="Jupyter AMD pytorch notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/rocm/pytorch/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-jupyter-pytorch-ubi9-python-3.11"

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY ${SOURCE_CODE}/Pipfile.lock ./
# Copy utility script
COPY ${SOURCE_CODE}/de-vendor-torch.sh ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock && \
    # De-vendor the ROCm libs that are embedded in Pytorch \
    ./de-vendor-torch.sh && \
    rm ./de-vendor-torch.sh && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
    sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && fix-permissions /opt/app-root -P
