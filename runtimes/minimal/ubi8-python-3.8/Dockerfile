ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-runtime-minimal-ubi8-python-3.8" \
    summary="Runtime minimal image for ODH notebooks" \
    description="Runtime minimal image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    io.k8s.display-name="Runtime minimal image for ODH notebooks" \
    io.k8s.description="Runtime minimal image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/runtimes/minimal/ubi8-python-3.8" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:runtime-minimal-ubi8-python-3.8"

WORKDIR /opt/app-root/bin

# Install Python packages from Pipfile.lock
COPY Pipfile.lock ./
# Copy Elyra dependencies for air-gapped enviroment
COPY utils ./utils/

RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.8/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
