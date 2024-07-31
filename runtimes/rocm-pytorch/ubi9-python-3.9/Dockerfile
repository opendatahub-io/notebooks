ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-runtime-rocm-pytorch-ubi9-python-3.9" \
    summary="Runtime ROCm pytorch notebook image for ODH notebooks" \
    description="Runtime ROCm pytorch notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Runtime ROCm pytorch notebook image for ODH notebooks" \
    io.k8s.description="Runtime ROCm pytorch notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/runtimes/rocm-pytorch/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-runtime-pytorch-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

# Install Python packages from Pipfile.lock
COPY Pipfile.lock ./
# Copy Elyra dependencies for air-gapped enviroment
COPY utils ./utils/
# Copy utility script
COPY de-vendor-torch.sh ./

RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # De-vendor the ROCm libs that are embedded in Pytorch \
    ./de-vendor-torch.sh && \
    rm ./de-vendor-torch.sh && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
