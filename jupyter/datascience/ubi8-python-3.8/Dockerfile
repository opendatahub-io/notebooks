ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-datascience-ubi8-python-3.8" \
    summary="Jupyter data science notebook image for ODH notebooks" \
    description="Jupyter data science notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    io.k8s.display-name="Jupyter data science notebook image for ODH notebooks" \
    io.k8s.description="Jupyter data science notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/datascience/ubi8-python-3.8" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:jupyter-datascience-ubi8-python-3.8"

WORKDIR /opt/app-root/bin

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY Pipfile.lock ./
# Copy Elyra setup to utils so that it's sourced at startup
COPY jupyter_elyra_config.py setup-elyra.sh ./utils/

RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # Explicitly enable jupyterlab_s3_browser plugin \
    jupyter serverextension enable --py jupyterlab_s3_browser && \
    # Remove Elyra logo from JupyterLab because this is not a pure Elyra image \
    sed -i 's/widget\.id === \x27jp-MainLogo\x27/widget\.id === \x27jp-MainLogo\x27 \&\& false/' /opt/app-root/share/jupyter/labextensions/@elyra/theme-extension/static/lib_index_js.*.js && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y \
    sed -i -e "s/Python.*/$(python --version)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Remove default Elyra runtime-images \
    rm /opt/app-root/share/jupyter/metadata/runtime-images/*.json && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.8/site-packages && \
    fix-permissions /opt/app-root -P

# Copy Elyra runtime-images definitions and set the version
COPY runtime-images/ /opt/app-root/share/jupyter/metadata/runtime-images/

WORKDIR /opt/app-root/src
