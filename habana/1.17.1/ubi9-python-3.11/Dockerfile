# Copyright (c) 2024 Habana Labs, Ltd.
#
# SPDX-License-Identifier: Apache-2.0
#
# This Dockerfile contains our own setup for Notebokks and Habana's 1.17.1 base installer image
# Reference: https://github.com/HabanaAI/Setup_and_Install/blob/1.17.1/dockerfiles/base/Dockerfile.rhel9.4
#
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

## Label the image with details required by ODH
LABEL name="odh-notebook-habana-jupyter-1.17.1-ubi9-python-3.11" \
    summary="Jupyter HabanaAI 1.17.1 notebook image for ODH notebooks" \
    description="Jupyter HabanaAI 1.17.1 notebook image with base Python 3.11 builder image based on ubi9 for ODH notebooks" \
    io.k8s.display-name="Jupyter HabanaAI 1.17.1 notebook image for ODH notebooks" \
    io.k8s.description="Jupyter HabanaAI 1.17.1 notebook image with base Python 3.11 builder image based on ubi9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/habana/1.17.1/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:habana-jupyter-1.17.1-ubi9-python-3.11"

ARG ARTIFACTORY_URL="vault.habana.ai"
ARG VERSION="1.17.1"
ARG REVISION="40"

###
# 1. Install EPEL repository
# 2. Install CentOS 9 repositories
# 3. Install required packages
# 4. Install Habana packages
# 5. Extra settings for Python
# 6. Install software and packages

USER root

# 1. Install EPEL repository
# -----------------------------
RUN dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    dnf clean all && rm -rf /var/cache/yum

# 2. Install CentOS 9 repositories
# -----------------------------
RUN echo "[BaseOS]" > /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "name=CentOS Linux 9 - BaseOS" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "baseurl=https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "gpgkey=https://www.centos.org/keys/RPM-GPG-KEY-CentOS-Official-SHA256" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo && \
    echo "gpgcheck=1" >> /etc/yum.repos.d/CentOS-Linux-BaseOS.repo

RUN echo "[centos9]" > /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "name=CentOS Linux 9 - AppStream" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "baseurl=https://mirror.stream.centos.org/9-stream/AppStream/x86_64/os" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "gpgkey=https://www.centos.org/keys/RPM-GPG-KEY-CentOS-Official-SHA256" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo && \
    echo "gpgcheck=1" >> /etc/yum.repos.d/CentOS-Linux-AppStream.repo

RUN echo "[CRB]" > /etc/yum.repos.d/CentOS-Linux-CRB.repo && \
    echo "name=CentOS Linux 9 - CRB" >> /etc/yum.repos.d/CentOS-Linux-CRB.repo && \
    echo "baseurl=https://mirror.stream.centos.org/9-stream/CRB/x86_64/os" >> /etc/yum.repos.d/CentOS-Linux-CRB.repo && \
    echo "gpgkey=https://www.centos.org/keys/RPM-GPG-KEY-CentOS-Official-SHA256" >> /etc/yum.repos.d/CentOS-Linux-CRB.repo && \
    echo "gpgcheck=1" >> /etc/yum.repos.d/CentOS-Linux-CRB.repo

# 3. Install required packages
# -----------------------------
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
    python3-devel \
    openssh-clients \
    openssl-1:3.0.7-27.el9 \
    openssl-devel-1:3.0.7-27.el9 \
    libjpeg-devel \
    openssh-server \
    lsb_release \
    wget \
    git \
    libffi-devel \
    bzip2-devel \
    zlib-devel \
    mesa-libGL \
    iproute \
    python3.11 \
    python3.11-pip \
    python3.11-devel \
    ffmpeg-free \
    perl-Net-SSLeay-1.92-2.el9 \
    python3-dnf-plugin-versionlock && \
    # update pkgs (except OS version) for resolving potentials CVEs
    dnf versionlock add redhat-release* openssl* perl-Net-SSLeay && \
    dnf update -y --nobest && \
    dnf clean all && rm -rf /var/cache/yum

# 4. Install Habana packages
# -----------------------------
COPY install_efa.sh .
RUN ./install_efa.sh && rm install_efa.sh && rm -rf /etc/ld.so.conf.d/efa.conf /etc/profile.d/efa.sh

ENV FI_EFA_USE_DEVICE_RDMA=1
ENV LD_LIBRARY_PATH=$LIBFABRIC_ROOT/lib:${MPI_ROOT}/lib:/usr/lib/habanalabs:$LD_LIBRARY_PATH
ENV LIBFABRIC_ROOT="/opt/habanalabs/libfabric-${LIBFABRIC_VERSION}"
ENV LIBFABRIC_VERSION="1.20.0"
ENV MPI_ROOT=/opt/amazon/openmpi
ENV MPICC=${MPI_ROOT}/bin/mpicc
ENV OPAL_PREFIX=${MPI_ROOT}
ENV PATH=${LIBFABRIC_ROOT}/bin:${MPI_ROOT}/bin:$PATH
ENV RDMAV_FORK_SAFE=1

RUN echo "[habanalabs]" > /etc/yum.repos.d/habanalabs.repo && \
    echo "name=Habana RH9 Linux repo" >> /etc/yum.repos.d/habanalabs.repo && \
    echo "baseurl=https://${ARTIFACTORY_URL}/artifactory/rhel/9/9.4" >> /etc/yum.repos.d/habanalabs.repo && \
    echo "gpgkey=https://${ARTIFACTORY_URL}/artifactory/api/v2/repositories/rhel/keyPairs/primary/public" >> /etc/yum.repos.d/habanalabs.repo && \
    echo "gpgcheck=1" >> /etc/yum.repos.d/habanalabs.repo

# for Habana GPG key with SHA-1 signature
RUN update-crypto-policies --set DEFAULT:SHA1

RUN dnf install -y habanalabs-rdma-core-"$VERSION"-"$REVISION".el9 \
    habanalabs-thunk-"$VERSION"-"$REVISION".el9 \
    habanalabs-firmware-tools-"$VERSION"-"$REVISION".el9 \
    habanalabs-graph-"$VERSION"-"$REVISION".el9 && \
    rm -f /etc/yum.repos.d/habanalabs.repo && rm -f /etc/yum.repos.d/habana.repo && rm -rf /tmp/* && \
    dnf clean all && rm -rf /var/cache/yum

RUN rpm -V habanalabs-rdma-core && rpm -V habanalabs-thunk && rpm -V habanalabs-firmware-tools && rpm -V habanalabs-graph

# There is no need to store pip installation files inside docker image
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=on
ENV RDMA_CORE_LIB=${RDMA_CORE_ROOT}/build/lib
ENV RDMA_CORE_ROOT=/opt/habanalabs/rdma-core/src

RUN wget -nv -O /tmp/libfabric-${LIBFABRIC_VERSION}.tar.bz2 https://github.com/ofiwg/libfabric/releases/download/v${LIBFABRIC_VERSION}/libfabric-${LIBFABRIC_VERSION}.tar.bz2 && \
    cd /tmp/ && tar xf /tmp/libfabric-${LIBFABRIC_VERSION}.tar.bz2 --no-same-owner && \
    cd /tmp/libfabric-${LIBFABRIC_VERSION} && \
    ./configure --prefix=$LIBFABRIC_ROOT --enable-psm3-verbs --enable-verbs=yes --with-synapseai=/usr && \
    make && make install && cd / && rm -rf /tmp/libfabric-${LIBFABRIC_VERSION}.tar.bz2 /tmp/libfabric-${LIBFABRIC_VERSION}

RUN wget -nv -O /tmp/main.zip https://github.com/HabanaAI/hccl_ofi_wrapper/archive/refs/heads/main.zip && \
    unzip /tmp/main.zip -d /tmp && \
    cd /tmp/hccl_ofi_wrapper-main && \
    make && cp -f libhccl_ofi_wrapper.so /usr/lib/habanalabs/libhccl_ofi_wrapper.so && \
    cd / && \
    rm -rf /tmp/main.zip /tmp/hccl_ofi_wrapper-main

# 5. Extra settings for Python
# -----------------------------
RUN alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 2 && \
    alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1 && \
    alternatives --set python3 /usr/bin/python3.11 && \
    alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 2 && \
    alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.9 1 && \
    alternatives --set pip3 /usr/bin/pip3.11

RUN python3.11 -m pip install pip==23.3.1 setuptools==67.3.3 wheel==0.38.4

RUN ln -s /usr/bin/python3 /usr/bin/python

RUN python3.11 -m pip install habana_media_loader=="${VERSION}"."${REVISION}"

# SSH configuration necessary to support mpi-operator v2
RUN mkdir -p /var/run/sshd && \
    sed -i 's/[ #]\(.*StrictHostKeyChecking \).*/ \1no/g' /etc/ssh/ssh_config && \
    sed -i 's/#\(ForwardAgent \).*/\1yes/g' /etc/ssh/ssh_config && \
    echo "    UserKnownHostsFile /dev/null" >> /etc/ssh/ssh_config && \
    sed -i 's/#\(StrictModes \).*/\1no/g' /etc/ssh/sshd_config && \
    ssh-keygen -A && \
    mkdir -p /var/run/sshd && echo "/usr/sbin/sshd -p 3022" | tee -a ~/.bashrc

# 6. Install software and packages
# -----------------------------
ENV GC_KERNEL_PATH=/usr/lib/habanalabs/libtpc_kernels.so
ENV HABANA_LOGS=/var/log/habana_logs/
ENV HABANA_SCAL_BIN_PATH=/opt/habanalabs/engines_fw
ENV HABANA_PLUGINS_LIB_PATH=/opt/habanalabs/habana_plugins
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV PIP_NO_CACHE_DIR=off
ENV PATH=$HOME/.local/bin/:$PATH
ENV PYTHON_VERSION=3.11
ENV PYTHONIOENCODING=UTF-8
ENV PYTHONUNBUFFERED=1

ENV BASH_ENV="${APP_ROOT}/bin/activate"
ENV ENV="${APP_ROOT}/bin/activate"
ENV PROMPT_COMMAND=". ${APP_ROOT}/bin/activate"

ENV HOME="${APP_ROOT}/src"

WORKDIR ${HOME}

RUN python3.11 -m venv --system-site-packages ${APP_ROOT} && \
    chown -R 1001:0 ${APP_ROOT} && \
    fix-permissions ${APP_ROOT} -P && \
    rpm-file-permissions && \
    echo "unset BASH_ENV PROMPT_COMMAND ENV" >> ${APP_ROOT}/bin/activate

# Apparently the following is needed due to training options.
# More information can be seen in the official documentation:
#   - https://instructlab.readthedocs.io/latest/habana-gaudi.html#install-and-run-instructlab-with-intel-gaudi
ENV TSAN_OPTIONS='ignore_noninstrumented_modules=1'

# For AML/CentOS/RHEL ca-cert file is expected exactly under /etc/ssl/certs/ca-certificates.crt
# otherwise curl will fail during access to S3 AWS storage
RUN ln -s /etc/ssl/certs/ca-bundle.crt /etc/ssl/certs/ca-certificates.crt

WORKDIR /opt/app-root/bin

# Install micropipenv to deploy packages from Pipfile.lock
RUN pip install --no-cache-dir -U "micropipenv[toml]"

# Install Python dependencies from Pipfile.lock file
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
    fix-permissions /opt/app-root -P

USER 1001

WORKDIR /opt/app-root/src