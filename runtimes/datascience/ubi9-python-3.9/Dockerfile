ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-runtime-datascience-ubi9-python-3.9" \
    summary="Runtime data science notebook image for ODH notebooks" \
    description="Runtime data science notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Runtime data science notebook image for ODH notebooks" \
    io.k8s.description="Runtime data science notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/runtimes/datascience/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:runtime-datascience-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

# Install Python packages from pyproject.toml and poetry.lock files
COPY pyproject.toml poetry.lock ./
# Copy Elyra dependencies for air-gapped enviroment
COPY utils ./utils/

RUN echo "Installing softwares and packages" && \
    micropipenv install --method poetry && \
    rm -f ./pyproject.toml ./poetry.lock && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
