ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG AUTHORITATIVE_SOURCE_URL
ARG BUILD_COMMIT_REF
ARG IMAGE_REGISTRY

LABEL name="odh-notebook-runtime-datascience-ubi8-python-3.8" \
    summary="Runtime data science notebook image for ODH notebooks" \
    description="Runtime data science notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    io.k8s.display-name="Runtime data science notebook image for ODH notebooks" \
    io.k8s.description="Runtime data science notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    authoritative-source-url="${AUTHORITATIVE_SOURCE_URL}" \
    io.openshift.build.commit.ref="${BUILD_COMMIT_REF}" \
    io.openshift.build.source-location="${AUTHORITATIVE_SOURCE_URL}/tree/${BUILD_COMMIT_REF}/runtimes/datascience/ubi8-python-3.8" \
    io.openshift.build.image="${IMAGE_REGISTRY}:runtime-datascience-ubi8-python-3.8"

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
