FROM registry.redhat.io/rhel9/python-39:latest

# Access the client's secret for the subscription manager from the environment variable
ARG SECRET_DIR=/opt/app-root/src/.sec
ARG SERVERURL_DEFAULT=""
ARG BASEURL_DEFAULT=""

LABEL name="odh-notebook-rocm-python-3.9" \
      summary="ROCm Python 3.9 base image for ODH notebooks" \
      description="ROCm Python 3.9 builder image based on RHEL Stream 9 for ODH notebooks" \
      io.k8s.display-name="ROCm Python 3.9 base image for ODH notebooks" \
      io.k8s.description="ROCm Python 3.9 builder image based on Rhel9 for ODH notebooks" \
      authoritative-source-url="https://github.com/red-hat-data-services/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/red-hat-data-services/notebooks/tree/main/amd/rhel9-python-3.9"

WORKDIR /opt/app-root/bin

ARG ROCM_VERSION=6.1
ARG AMDGPU_VERSION=6.1

# Install micropipenv to deploy packages from Pipfile.lock
RUN pip install --no-cache-dir -U "micropipenv[toml]"
COPY Pipfile.lock ./
RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

USER 0

# Run the subscription manager command using the provided credentials. Only include --serverurl and --baseurl if they are provided
RUN SERVERURL=$(cat ${SECRET_DIR}/SERVERURL 2>/dev/null || echo ${SERVERURL_DEFAULT}) && \
    BASEURL=$(cat ${SECRET_DIR}/BASEURL 2>/dev/null || echo ${BASEURL_DEFAULT}) && \
    USERNAME=$(cat ${SECRET_DIR}/USERNAME) && \
    PASSWORD=$(cat ${SECRET_DIR}/PASSWORD) && \
    subscription-manager register \
    ${SERVERURL:+--serverurl=$SERVERURL} \
    ${BASEURL:+--baseurl=$BASEURL} \
    --username=$USERNAME \
    --password=$PASSWORD \
    --force \
    --auto-attach

# Install required packages 
RUN yum -y install git java-1.8.0-openjdk && \
    yum clean all && rm -rf /var/cache/yum

# Install ROCm AMD from:
# https://github.com/ROCm/ROCm-docker/blob/master/dev/Dockerfile-RHEL-7-complete
# Enable epel-release repositories
RUN subscription-manager repos --enable codeready-builder-for-rhel-9-x86_64-rpms && \
    yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    yum -y install bc bridge-utils glibc.i686 \
    numactl-libs libssh libunwind-devel \
    libunwind pciutils pciutils-libs \
    re2c doxygen elfutils-libelf-devel \
    expect numactl-devel pciutils-devel \
    qemu-kvm subversion dkms dpkg \
    dpkg-dev dpkg-perl fakeroot mesa-libGL && \
    yum clean all && rm -rf /var/cache/yum

# On RHEL, install package RHEL repository:

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
    yum clean all && rm -rf /var/cache/yum

# Restore notebook user workspace
USER 1001

# Install the oc client
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
