ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-intel-base-gpu-ubi9-python-3.9" \
      summary="Intel® XPU base image for ODH notebooks based on ubi9" \
      description="Base Intel® XPU base image builder image based on ubi9 for ODH notebooks" \
      io.k8s.display-name="Base Intel® XPU base image for ODH notebooks based on ubi9" \
      io.k8s.description="Base Intel® XPU base image builder image based on ubi9 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/intel/base/gpu/ubi9-python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:intel-base-gpu-ubi9-python-3.9"

USER 0
WORKDIR /opt/app-root/src

RUN . /etc/os-release && \
    dnf install -y 'dnf-command(config-manager)' && \
    dnf config-manager --add-repo \
        https://repositories.intel.com/gpu/rhel/${VERSION_ID}/lts/2350/unified/intel-gpu-${VERSION_ID}.repo  && \
    dnf install -y \
        intel-opencl \
        level-zero intel-level-zero-gpu level-zero-devel \
        intel-metrics-discovery \
        intel-metrics-library  && \
    dnf clean all -y && \
    rm -rf /var/cache/dnf/*

RUN dnf update -y && \
    rpm -ivh https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os/Packages/numactl-libs-2.0.16-3.el9.x86_64.rpm && \
    rpm -ivh https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os/Packages/numactl-2.0.16-3.el9.x86_64.rpm && \
    dnf install -y \
        git \
        rsync \
        unzip \
        wget && \
    dnf clean all && \
    rm -rf /var/cache/dnf/*


USER 1001
