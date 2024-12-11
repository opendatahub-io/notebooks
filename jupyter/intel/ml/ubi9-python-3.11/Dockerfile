ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG REUSABLE_UTILS=jupyter/utils
ARG SOURCE_CODE=jupyter/intel/ml/ubi9-python-3.11

LABEL name="odh-notebook-jupyter-intel-ml-ubi9-python-3.11" \
    summary="Jupyter Intel® optimized ML notebook image for ODH notebooks." \
    description="Jupyter Intel® ML notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter Intel® optimized ML notebook image for ODH notebooks." \
    io.k8s.description="Jupyter Intel® optimized ML notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/intel/ml/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:jupyter-intel-ml-ubi9-python-3.11"

WORKDIR /opt/app-root/bin

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY ${SOURCE_CODE}/Pipfile.lock Pipfile.lock

COPY --chown=1001:0 ${SOURCE_CODE}/.patch_sklearn.py /opt/app-root/bin/.patch_sklearn.py
ENV PYTHONSTARTUP="/opt/app-root/bin/.patch_sklearn.py"

RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
    fix-permissions /opt/app-root -P

#Replacing kernel manually with oneapi variable setting script
COPY --chown=1001:0 ${SOURCE_CODE}/start-notebook.sh /opt/app-root/bin
COPY --chown=1001:0 ${SOURCE_CODE}/builder /opt/app-root/builder
COPY --chown=1001:0 ${REUSABLE_UTILS} /opt/app-root/bin/utils

# Apply JupyterLab addons
RUN /opt/app-root/bin/utils/addons/apply.sh

WORKDIR /opt/app-root/src

ENV JUPYTER_PRELOAD_REPOS="https://github.com/IntelAI/oneAPI-samples"
ENV REPO_BRANCH="main"

ENTRYPOINT ["bash", "-c", "/opt/app-root/builder/run"]
