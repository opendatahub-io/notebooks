ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-intel-runtime-tensorflow-xpu-ubi9-python-3.9" \
    summary="Runtime Intel® optimized TensorFlow XPU notebook image for ODH notebooks" \
    description="Runtime Intel® optimized TesorFlow XPU notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Runtime Intel® optimized TensorFlow XPU notebook image for ODH notebooks" \
    io.k8s.description="Runtime Intel® optimized TensorFlow XPU notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/intel/runtimes/tensorflow/xpu/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:intel-runtime-tensorflow-xpu-ubi9-python-3.9"

USER root

ARG ONEAPI_VERSION=2024.0
COPY oneAPI.repo /etc/yum.repos.d/oneAPI.repo

RUN dnf update -y && \
    dnf install -y intel-oneapi-compiler-dpcpp-cpp-runtime-${ONEAPI_VERSION} \
    intel-oneapi-mkl-${ONEAPI_VERSION} \
    intel-oneapi-dnnl-${ONEAPI_VERSION} && \
    dnf clean all -y && \
    rm -rf /var/cache/dnf/* && \
    rm /etc/yum.repos.d/oneAPI.repo

USER 1001

WORKDIR /opt/app-root/bin

# Install Python packages from Pipfile.lock
COPY Pipfile.lock Pipfile.lock

# Copy Elyra dependencies for air-gapped enviroment
COPY utils utils

#Virtualenv creates a symlink of lib to lib64. That causes issues with importing ITEX since both locations will have ITEX library and it will conflict.
RUN unlink /opt/app-root/lib64 && \
    cp -r /opt/app-root/lib /opt/app-root/lib64 && \
    echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
