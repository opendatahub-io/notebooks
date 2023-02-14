ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-datascience-ubi9-python-3.9" \
    summary="Jupyter data science notebook image for ODH notebooks" \
    description="Jupyter data science notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter data science notebook image for ODH notebooks" \
    io.k8s.description="Jupyter data science notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/datascience/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/notebooks:jupyter-datascience-ubi9-python-3.9"

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# Remove Elyra logo from JupyterLab because this is not a pure Elyra image \
RUN sed -i 's/widget\.id === \x27jp-MainLogo\x27/widget\.id === \x27jp-MainLogo\x27 \&\& false/' /opt/app-root/share/jupyter/labextensions/@elyra/theme-extension/static/lib_index_js.*.js

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P
