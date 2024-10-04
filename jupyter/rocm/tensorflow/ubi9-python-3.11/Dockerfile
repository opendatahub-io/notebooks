ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-rocm-tensorflow-ubi9-python-3.11" \
    summary="Jupyter AMD tensorflow notebook image for ODH notebooks" \
    description="Jupyter AMD tensorflow notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter AMD tensorflow notebook image for ODH notebooks" \
    io.k8s.description="Jupyter AMD tensorflow notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/rocm/tensorflow/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-jupyter-tensorflow-ubi9-python-3.11"

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY Pipfile.lock ./

# Temporary:Workaround for fixing the kfp-kubernetes 1.0.0 for elyra pipeline execution
# TODO: Remove this patch once the issue is fixed with kfp-kubernetes upgrade.
COPY utils ./utils/
RUN patch /opt/app-root/lib/python3.11/site-packages/elyra/templates/kubeflow/v2/python_dsl_template.jinja2 -i utils/python_dsl_template.patch && \
    echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y \
    sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && fix-permissions /opt/app-root -P
