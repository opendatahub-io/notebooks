# Copyright (c) 2022 Habana Labs, Ltd.
#
# SPDX-License-Identifier: Apache-2.0
#
# HabanaLabs Dockerfile base installer layer for RedHat 8.6
# Reference: https://github.com/HabanaAI/Setup_and_Install/blob/1.11.0/dockerfiles/base/Dockerfile.rhel8.6 
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG ARTIFACTORY_URL="vault.habana.ai"
ARG VERSION="1.11.0"
ARG REVISION="587"
ARG PT_VERSION="2.0.1"

USER root

RUN dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm && \
    dnf clean all && rm -rf /var/cache/yum

RUN echo "[appstream]" > /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "name=CentOS Linux 8 - AppStream" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "baseurl=https://vault.centos.org/\$releasever-stream/AppStream/\$basearch/os/" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo


RUN echo "[BaseOS]" > /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "name=CentOS Linux 8 - BaseOS" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "baseurl=https://vault.centos.org/\$releasever-stream/BaseOS/\$basearch/os/" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo

RUN dnf install -y \
    clang \
    cmake3 \
    cpp \
    gcc \
    gcc-c++ \
    glibc \
    glibc-headers \
    glibc-devel \
    jemalloc \
    libarchive \
    libksba \
    unzip \
    llvm \
    lsof \
    python38-devel \
    openssh-clients \
    libjpeg-devel \
    openssh-server \
    redhat-lsb-core \
    wget \
    git \
    mesa-libGL \
    python3-dnf-plugin-versionlock && \
    # update pkgs (except OS version) for resolving potentials CVEs
    dnf versionlock add redhat-release* && \
    dnf update -y && \
    dnf clean all && rm -rf /var/cache/yum

ENV LD_LIBRARY_PATH=/usr/lib/habanalabs:$LD_LIBRARY_PATH
ENV RDMAV_FORK_SAFE=1

RUN echo "[habanalabs]" > /etc/yum.repos.d/habanalabs.repo && \
    echo "name=Habana RH8 Linux repo" >> /etc/yum.repos.d/habanalabs.repo && \
    echo "baseurl=https://${ARTIFACTORY_URL}/artifactory/rhel/8/8.6" >> /etc/yum.repos.d/habanalabs.repo && \
    echo "gpgkey=https://${ARTIFACTORY_URL}/artifactory/rhel/8/8.6/repodata/repomd.xml.key" >> /etc/yum.repos.d/habanalabs.repo

RUN echo "[powertools]" > /etc/yum.repos.d/powertools.repo && \
    echo "name=powertools" >> /etc/yum.repos.d/powertools.repo && \
    echo "baseurl=https://vault.centos.org/\$releasever-stream/PowerTools/\$basearch/os/"  >> /etc/yum.repos.d/powertools.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/powertools.repo

RUN dnf install -y habanalabs-rdma-core-"$VERSION"-"$REVISION".el8 \
        habanalabs-thunk-"$VERSION"-"$REVISION".el8 \
        habanalabs-firmware-tools-"$VERSION"-"$REVISION".el8 \
        habanalabs-graph-"$VERSION"-"$REVISION".el8 && \
    rm -f /etc/yum.repos.d/habanalabs.repo && rm -rf /tmp/* && \
    dnf clean all && rm -rf /var/cache/yum

RUN rpm -V habanalabs-rdma-core && rpm -V habanalabs-thunk && rpm -V habanalabs-firmware-tools && rpm -V habanalabs-graph

# There is no need to store pip installation files inside docker image
ENV PIP_NO_CACHE_DIR=on
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV RDMA_CORE_ROOT=/opt/habanalabs/rdma-core/src
ENV RDMA_CORE_LIB=${RDMA_CORE_ROOT}/build/lib

# Install python packages 
# RUN python3.8 -m pip install hpu_media_loader=="${VERSION}"."${REVISION}"
# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

RUN echo "export LANG=en_US.UTF-8" >> /root/.bashrc
RUN export LANG=en_US.UTF-8
ENV GC_KERNEL_PATH=/usr/lib/habanalabs/libtpc_kernels.so
ENV HABANA_LOGS=/var/log/habana_logs/
ENV HABANA_SCAL_BIN_PATH=/opt/habanalabs/engines_fw
ENV HABANA_PLUGINS_LIB_PATH=/opt/habanalabs/habana_plugins

## Install habana tensorflow
# Reference: https://github.com/HabanaAI/Setup_and_Install/blob/1.11.0/dockerfiles/tensorflow/Dockerfile.rhel8.6
# For AML/CentOS/RHEL OS'es TFIO_DATAPATH have to be specified to import tensorflow_io lib correctly
ENV TFIO_DATAPATH=/opt/app-root/src/python3.8/site-packages/

# For AML/CentOS/RHEL ca-cert file is expected exactly under /etc/ssl/certs/ca-certificates.crt
# otherwise curl will fail during access to S3 AWS storage
RUN ln -s /etc/ssl/certs/ca-bundle.crt /etc/ssl/certs/ca-certificates.crt

## Install habana pytorch
# Reference: https://github.com/HabanaAI/Setup_and_Install/blob/1.11.0/dockerfiles/pytorch/Dockerfile.rhel8.6
ENV LANG=en_US.UTF-8
ENV PYTHONPATH=/root:/usr/lib/habanalabs/

RUN dnf install -y \
    curl \
    cairo-devel \
    numactl-devel \
    iproute \
    which \
    zlib-devel \
    lapack-devel \
    openblas-devel \
    numactl \
    gperftools-devel && \
    dnf clean all && rm -rf /var/cache/yum

RUN wget --no-verbose https://"${ARTIFACTORY_URL}"/artifactory/gaudi-pt-modules/"${VERSION}"/"${REVISION}"\
/pytorch/rhel86/pytorch_modules-v"${PT_VERSION}"_"${VERSION}"_"${REVISION}".tgz && \
    mkdir /root/habanalabs /root/habanalabs/pytorch_temp && \
    tar -xf pytorch_modules-v"${PT_VERSION}"_"${VERSION}"_"${REVISION}".tgz -C /root/habanalabs/pytorch_temp/. && \
    pip3 install /root/habanalabs/pytorch_temp/*.whl && \
    pip3 install $(grep "lightning" /root/habanalabs/pytorch_temp/requirements-pytorch.txt) && \
    pip3 install tensorboard~=2.12.2 protobuf==3.20.3 && \
    pip3 uninstall -y pillow && \
    pip3 uninstall -y pillow-simd && \
    pip3 install pillow-simd==7.0.0.post3 && \
    rm -rf /root/habanalabs/pytorch_temp/ && \
    rm -rf pytorch_modules-v"${PT_VERSION}"_"${VERSION}"_"${REVISION}".tgz &&\
    echo "source /etc/profile.d/habanalabs.sh" >> ~/.bashrc

ENV LD_PRELOAD=/lib64/libtcmalloc.so.4
ENV TCMALLOC_LARGE_ALLOC_REPORT_THRESHOLD=7516192768

RUN dnf clean all && rm -rf /var/cache/dnf && rm -rf /tmp/*

## Label the image with details required by ODH
LABEL name="odh-notebook-habana-jupyter-1.11.0-ubi8-python-3.8" \
    summary="Jupyter HabanaAI 1.11.0 notebook image for ODH notebooks" \
    description="Jupyter HabanaAI 1.11.0 notebook image with base Python 3.8 builder image based on ubi8 for ODH notebooks" \
    io.k8s.display-name="Jupyter HabanaAI 1.11.0 notebook image for ODH notebooks" \
    io.k8s.description="Jupyter HabanaAI 1.11.0 notebook image with base Python 3.8 builder image based on ubi8 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/habana/1.11.0/ubi8-python-3.8" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:habana-jupyter-1.11.0-ubi8-python-3.8"

# Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x
RUN sed -i -e "s/Python.*/$(python --version| cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.8/site-packages && \
    fix-permissions /opt/app-root -P

USER 1001

WORKDIR /opt/app-root/src