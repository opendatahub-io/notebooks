ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-intel-runtime-ml-ubi9-python-3.9" \
    summary="Runtime Intel® optimized ML notebook image for ODH notebooks" \
    description="Runtime Intel® optimized ML notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Runtime Intel® optimized ML notebook image for ODH notebooks" \
    io.k8s.description="Runtime Intel® optimized ML notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/intel/runtimes/ml/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:intel-runtime-ml-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

# Install Python packages from pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock ./

# Copy Elyra dependencies for air-gapped enviroment
COPY utils utils

COPY --chown=1001:0 .patch_sklearn.py /opt/app-root/bin/.patch_sklearn.py
ENV PYTHONSTARTUP="/opt/app-root/bin/.patch_sklearn.py"

#Virtualenv creates a symlink of lib to lib64. That causes issues with importing ITEX since both locations will have ITEX library and it will conflict.
RUN echo "Installing softwares and packages" && \
    micropipenv install --method poetry && \
    rm -f ./pyproject.toml ./poetry.lock && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
