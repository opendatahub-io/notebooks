ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-intel-ml-ubi9-python-3.9" \
    summary="Jupyter Intel® optimized ML notebook image for ODH notebooks." \
    description="Jupyter Intel® ML notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter Intel® optimized ML notebook image for ODH notebooks." \
    io.k8s.description="Jupyter Intel® optimized ML notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/intel/ml/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:jupyter-intel-ml-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

# Install Python packages and Jupyterlab extensions from pyproject.toml and poetry.lock
COPY pyproject.toml poetry.lock ./

COPY --chown=1001:0 .patch_sklearn.py /opt/app-root/bin/.patch_sklearn.py
ENV PYTHONSTARTUP="/opt/app-root/bin/.patch_sklearn.py"

RUN echo "Installing softwares and packages" && \
    micropipenv install --method poetry && \
    rm -f ./pyproject.toml ./poetry.lock && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

#Replacing kernel manually with oneapi variable setting script
COPY --chown=1001:0 start-notebook.sh /opt/app-root/bin
COPY --chown=1001:0 builder /opt/app-root/builder
COPY --chown=1001:0 utils /opt/app-root/bin/utils

WORKDIR /opt/app-root/src

ENV JUPYTER_PRELOAD_REPOS="https://github.com/IntelAI/oneAPI-samples"
ENV REPO_BRANCH="main"

ENTRYPOINT ["bash", "-c", "/opt/app-root/builder/run"]
