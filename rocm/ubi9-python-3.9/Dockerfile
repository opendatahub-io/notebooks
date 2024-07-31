# Install ROCm AMD from:
# https://github.com/ROCm/ROCm-docker/blob/master/dev/Dockerfile-centos-7-complete
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
LABEL name="odh-notebook-rocm-python-3.9" \
      summary="ROCm Python 3.9 base image for ODH notebooks" \
      description="ROCm Python 3.9 builder image based on UBI9 for ODH notebooks" \
      io.k8s.display-name="ROCm Python 3.9 base image for ODH notebooks" \
      io.k8s.description="ROCm Python 3.9 builder image based on UBI9 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/rocm/ubi9-python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-ubi9-python-3.9"

USER 0
WORKDIR /opt/app-root/bin

# Please keep in sync with ROCm/python3.9 dependent images
ARG ROCM_VERSION=6.1
ARG AMDGPU_VERSION=6.1

# default: same targets and ROCm version as https://github.com/tiran/instructlab-containers/blob/main/containers/rocm/Containerfile.c9s#L47
ARG AMDGPU_TARGETS=gfx900;gfx906:xnack-;gfx908:xnack-;gfx90a:xnack-;gfx90a:xnack+;gfx942;gfx1030;gfx1100

# Enable epel-release repositories

# Install the ROCm rpms
RUN echo "[ROCm]" > /etc/yum.repos.d/rocm.repo && \
    echo "name=ROCm" >> /etc/yum.repos.d/rocm.repo && \
    echo "baseurl=https://repo.radeon.com/rocm/rhel9/$ROCM_VERSION/main" >> /etc/yum.repos.d/rocm.repo && \
    echo "enabled=1" >> /etc/yum.repos.d/rocm.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/rocm.repo && \
    echo "[amdgpu]" > /etc/yum.repos.d/amdgpu.repo && \
    echo "name=amdgpu" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "baseurl=https://repo.radeon.com/amdgpu/$AMDGPU_VERSION/rhel/9.4/main/x86_64" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "enabled=1" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/amdgpu.repo && \
    yum install -y rocm && \
    yum clean all && rm -rf /var/cache/yum && \
    # force remove 'rocm-llvm' from runtime, saves 3.6 GB on disk
    rpm -e --nodeps rocm-llvm && \
    # remove gfx files for unused ISAs, saves about 1.7 GB on disk
    # sed creates regular expression '.*\(gfx900\|gfx906\|...\).*'
    find /opt/rocm/lib/ -type f \
        -and -name '*gfx*' \
        -and -not -regex '.*\('$(echo $AMDGPU_TARGETS | sed -e 's/;/\\|/g' -e 's/:xnack[-+]//g')'\).*' \
        -print0 | xargs -0 rm -v

# Restore notebook user workspace
USER 1001
WORKDIR /opt/app-root/src
