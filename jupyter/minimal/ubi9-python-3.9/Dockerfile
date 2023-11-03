ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG AUTHORITATIVE_SOURCE_URL
ARG BUILD_COMMIT_REF
ARG IMAGE_REGISTRY

LABEL name="odh-notebook-jupyter-minimal-ubi9-python-3.9" \
    summary="Minimal Jupyter notebook image for ODH notebooks" \
    description="Minimal Jupyter notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Minimal Jupyter notebook image for ODH notebooks" \
    io.k8s.description="Minimal Jupyter notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="${AUTHORITATIVE_SOURCE_URL}" \
    io.openshift.build.commit.ref="${BUILD_COMMIT_REF}" \
    io.openshift.build.source-location="${AUTHORITATIVE_SOURCE_URL}/tree/${BUILD_COMMIT_REF}/jupyter/minimal/ubi9-python-3.9" \
    io.openshift.build.image="${IMAGE_REGISTRY}:jupyter-minimal-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

COPY utils utils/

COPY Pipfile.lock start-notebook.sh ./

# Install Python dependencies from Pipfile.lock file
RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# Disable announcement plugin of jupyterlab
RUN jupyter labextension disable "@jupyterlab/apputils-extension:announcements"

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
      fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src

# Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
RUN sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json

ENTRYPOINT ["start-notebook.sh"]

