ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG SOURCE_CODE=runtimes/rocm-pytorch/ubi9-python-3.11

LABEL name="odh-notebook-runtime-rocm-pytorch-ubi9-python-3.11" \
    summary="Runtime ROCm pytorch notebook image for ODH notebooks" \
    description="Runtime ROCm pytorch notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Runtime ROCm pytorch notebook image for ODH notebooks" \
    io.k8s.description="Runtime ROCm pytorch notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/runtimes/rocm-pytorch/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-runtime-pytorch-ubi9-python-3.11"

WORKDIR /opt/app-root/bin

# Install Python packages from Pipfile.lock
COPY ${SOURCE_CODE}/Pipfile.lock ./
# Copy Elyra dependencies for air-gapped enviroment
COPY ${SOURCE_CODE}/utils ./utils/
# Copy utility script
COPY ${SOURCE_CODE}/de-vendor-torch.sh ./

RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # De-vendor the ROCm libs that are embedded in Pytorch \
    ./de-vendor-torch.sh && \
    rm ./de-vendor-torch.sh && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
