# Copyright (c) 2024 Habana Labs, Ltd.
#
# SPDX-License-Identifier: Apache-2.0
#
# HabanaLabs Dockerfile base installer layer for RedHat 9.4
FROM registry.access.redhat.com/ubi9/ubi:9.4
ARG ARTIFACTORY_URL="vault.habana.ai"
ARG VERSION="1.17.1"
ARG REVISION="40"

LABEL vendor="Habanalabs Ltd."
LABEL release="${VERSION}-${REVISION}"

COPY LICENSE /licenses/

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

RUN dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    dnf clean all && rm -rf /var/cache/yum

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

RUN alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 2 && \
    alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1 && \
    alternatives --set python3 /usr/bin/python3.11 && \
    alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 2 && \
    alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.9 1 && \
    alternatives --set pip3 /usr/bin/pip3.11

COPY install_efa.sh .
RUN ./install_efa.sh && rm install_efa.sh && rm -rf /etc/ld.so.conf.d/efa.conf /etc/profile.d/efa.sh

ENV LIBFABRIC_VERSION="1.20.0"
ENV LIBFABRIC_ROOT="/opt/habanalabs/libfabric-${LIBFABRIC_VERSION}"
ENV MPI_ROOT=/opt/amazon/openmpi
ENV LD_LIBRARY_PATH=$LIBFABRIC_ROOT/lib:${MPI_ROOT}/lib:/usr/lib/habanalabs:$LD_LIBRARY_PATH
ENV PATH=${LIBFABRIC_ROOT}/bin:${MPI_ROOT}/bin:$PATH
ENV OPAL_PREFIX=${MPI_ROOT}
ENV MPICC=${MPI_ROOT}/bin/mpicc
ENV RDMAV_FORK_SAFE=1
ENV FI_EFA_USE_DEVICE_RDMA=1

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
ENV PIP_NO_CACHE_DIR=on
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV RDMA_CORE_ROOT=/opt/habanalabs/rdma-core/src
ENV RDMA_CORE_LIB=${RDMA_CORE_ROOT}/build/lib

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

ENV GC_KERNEL_PATH=/usr/lib/habanalabs/libtpc_kernels.so
ENV HABANA_LOGS=/var/log/habana_logs/
ENV HABANA_SCAL_BIN_PATH=/opt/habanalabs/engines_fw
ENV HABANA_PLUGINS_LIB_PATH=/opt/habanalabs/habana_plugins
