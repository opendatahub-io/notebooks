ARG BASE_IMAGE
FROM ${BASE_IMAGE}
LABEL name="odh-notebook-rocm-python-3.9" \
      summary="ROCm Python 3.9 base image for ODH notebooks" \
      description="ROCm Python 3.9 builder image based on CentOS Stream 9 for ODH notebooks" \
      io.k8s.display-name="ROCm Python 3.9 base image for ODH notebooks" \
      io.k8s.description="ROCm Python 3.9 builder image based on C9S for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/amd/python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-python-3.9"

USER 0
WORKDIR /opt/app-root/bin

ARG ROCM_VERSION=6.1
ARG AMDGPU_VERSION=6.1
# Base
RUN yum -y install git java-1.8.0-openjdk python; yum clean all
# Install ROCm AMD from:
# https://github.com/ROCm/ROCm-docker/blob/master/dev/Dockerfile-centos-7-complete
# Enable epel-release repositories
RUN yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    yum config-manager --set-enabled crb && \
    yum clean all && rm -rf /var/cache/yum


# Install required base build and packaging commands for ROCm
RUN yum -y install \
    bc \
    bridge-utils \
    glibc.i686 \
    numactl-libs \
    libssh \
    libunwind-devel \
    libunwind \
    pciutils \
    pciutils-libs \
    re2c \
    doxygen \
    elfutils-libelf-devel \
    expect \
    numactl-devel \
    pciutils-devel \
    qemu-kvm \
    subversion \
    dkms \
    dpkg \
    dpkg-dev \
    dpkg-perl && \
    yum clean all 
# These binaries are not available.
# devscripts \
# pth \
# libcxx-devel \


# Enable the epel repository for fakeroot
# RUN yum --enablerepo=extras install -y fakeroot
# RUN yum clean all
RUN yum install -y fakeroot && \
    yum clean all


# On CentOS, install package centos-release-scl available in CentOS repository:
# RUN yum install -y centos-release-scl

# Install the devtoolset-7 collection:
# RUN yum install -y devtoolset-7
# RUN yum install -y devtoolset-7-libatomic-devel devtoolset-7-elfutils-libelf-devel

# Install the ROCm rpms
RUN echo "[ROCm]" > /etc/yum.repos.d/rocm.repo && \
    echo "name=ROCm" >> /etc/yum.repos.d/rocm.repo && \
    echo "baseurl=https://repo.radeon.com/rocm/el9/$ROCM_VERSION/main" >> /etc/yum.repos.d/rocm.repo && \
    echo "enabled=1" >> /etc/yum.repos.d/rocm.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/rocm.repo

RUN echo "[amdgpu]" > /etc/yum.repos.d/amdgpu.repo && \
    echo "name=amdgpu" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "baseurl=https://repo.radeon.com/amdgpu/$AMDGPU_VERSION/el/9.2/main/x86_64" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "enabled=1" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/amdgpu.repo

# Install rocm and amdgpu binaries 
RUN yum install -y amdgpu-dkms rocm && \
    yum clean all

# Set ENV to enable devtoolset7 by default 
# Set ENV to enable devtoolset7 by default 
# ENV PATH=/opt/rh/devtoolset-7/root/usr/bin:/opt/rocm/hcc/bin:/opt/rocm/hip/bin:/opt/rocm/bin:/opt/rocm/hcc/bin:${PATH:+:${PATH}}
# ENV MANPATH=/opt/rh/devtoolset-7/root/usr/share/man:${MANPATH}
# ENV INFOPATH=/opt/rh/devtoolset-7/root/usr/share/info${INFOPATH:+:${INFOPATH}}
# ENV PCP_DIR=/opt/rh/devtoolset-7/root
# ENV PERL5LIB=/opt/rh/devtoolset-7/root//usr/lib64/perl5/vendor_perl:/opt/rh/devtoolset-7/root/usr/lib/perl5:/opt/rh/devtoolset-7/root//usr/share/perl5/
# ENV LD_LIBRARY_PATH=/opt/rocm/lib:/usr/local/lib:/opt/rh/devtoolset-7/root$rpmlibdir$rpmlibdir32${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
# ENV PYTHONPATH=/opt/rh/devtoolset-7/root/usr/lib64/python$pythonvers/site-packages:/opt/rh/devtoolset-7/root/usr/lib/python$pythonvers/
# ENV LDFLAGS="-Wl,-rpath=/opt/rh/devtoolset-7/root/usr/lib64 -Wl,-rpath=/opt/rh/devtoolset-7/root/usr/lib"

# Restore notebook user workspace
USER 1001
WORKDIR /opt/app-root/src
