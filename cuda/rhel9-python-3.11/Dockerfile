ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Access the client's secret for the subscription manager from the environment variable
ARG SECRET_DIR=/opt/app-root/src/.sec
ARG SERVERURL_DEFAULT=""
ARG BASEURL_DEFAULT=""

LABEL name="odh-notebook-cuda-rhel9-python-3.11" \
      summary="CUDA Python 3.11 base image for ODH notebooks" \
      description="CUDA Python 3.11 builder image based on RHEL9 for ODH notebooks" \
      io.k8s.display-name="CUDA Python 3.11 base image for ODH notebooks" \
      io.k8s.description="CUDA Python 3.11 builder image based on RHEL9 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/cuda/rhel9-python-3.11" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:cuda-rhel9-python-3.11"

# Install CUDA base from:
# https://gitlab.com/nvidia/container-images/cuda/-/tree/master/dist/12.4.1/ubi9/base
USER 0
WORKDIR /opt/app-root/bin

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

ENV NVARCH x86_64
ENV NVIDIA_REQUIRE_CUDA "cuda>=12.4 brand=tesla,driver>=470,driver<471 brand=unknown,driver>=470,driver<471 brand=nvidia,driver>=470,driver<471 brand=nvidiartx,driver>=470,driver<471 brand=geforce,driver>=470,driver<471 brand=geforcertx,driver>=470,driver<471 brand=quadro,driver>=470,driver<471 brand=quadrortx,driver>=470,driver<471 brand=titan,driver>=470,driver<471 brand=titanrtx,driver>=470,driver<471 brand=tesla,driver>=525,driver<526 brand=unknown,driver>=525,driver<526 brand=nvidia,driver>=525,driver<526 brand=nvidiartx,driver>=525,driver<526 brand=geforce,driver>=525,driver<526 brand=geforcertx,driver>=525,driver<526 brand=quadro,driver>=525,driver<526 brand=quadrortx,driver>=525,driver<526 brand=titan,driver>=525,driver<526 brand=titanrtx,driver>=525,driver<526 brand=tesla,driver>=535,driver<536 brand=unknown,driver>=535,driver<536 brand=nvidia,driver>=535,driver<536 brand=nvidiartx,driver>=535,driver<536 brand=geforce,driver>=535,driver<536 brand=geforcertx,driver>=535,driver<536 brand=quadro,driver>=535,driver<536 brand=quadrortx,driver>=535,driver<536 brand=titan,driver>=535,driver<536 brand=titanrtx,driver>=535,driver<536"
ENV NV_CUDA_CUDART_VERSION 12.4.127-1

COPY cuda/rhel9-python-3.11/cuda.repo-x86_64 /etc/yum.repos.d/cuda.repo

RUN NVIDIA_GPGKEY_SUM=d0664fbbdb8c32356d45de36c5984617217b2d0bef41b93ccecd326ba3b80c87 && \
    curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/rhel9/${NVARCH}/D42D0685.pub | sed '/^Version/d' > /etc/pki/rpm-gpg/RPM-GPG-KEY-NVIDIA && \
    echo "$NVIDIA_GPGKEY_SUM  /etc/pki/rpm-gpg/RPM-GPG-KEY-NVIDIA" | sha256sum -c --strict -

ENV CUDA_VERSION 12.4.1

# For libraries in the cuda-compat-* package: https://docs.nvidia.com/cuda/eula/index.html#attachment-a
RUN yum upgrade -y && yum install -y \
    cuda-cudart-12-4-${NV_CUDA_CUDART_VERSION} \
    cuda-compat-12-4 \
    && yum clean all \
    && rm -rf /var/cache/yum/*

# nvidia-docker 1.0
RUN echo "/usr/local/nvidia/lib" >> /etc/ld.so.conf.d/nvidia.conf && \
    echo "/usr/local/nvidia/lib64" >> /etc/ld.so.conf.d/nvidia.conf

ENV PATH /usr/local/nvidia/bin:/usr/local/cuda/bin:${PATH}
ENV LD_LIBRARY_PATH /usr/local/nvidia/lib:/usr/local/nvidia/lib64

COPY cuda/rhel9-python-3.11/NGC-DL-CONTAINER-LICENSE /

# nvidia-container-runtime
ENV NVIDIA_VISIBLE_DEVICES all
ENV NVIDIA_DRIVER_CAPABILITIES compute,utility

# Install CUDA runtime from:
# https://gitlab.com/nvidia/container-images/cuda/-/blob/master/dist/12.4.1/ubi9/runtime/Dockerfile
ENV NV_CUDA_LIB_VERSION 12.4.1-1
ENV NV_NVTX_VERSION 12.4.127-1
ENV NV_LIBNPP_VERSION 12.2.5.30-1
ENV NV_LIBNPP_PACKAGE libnpp-12-4-${NV_LIBNPP_VERSION}
ENV NV_LIBCUBLAS_VERSION 12.4.5.8-1
ENV NV_LIBNCCL_PACKAGE_NAME libnccl
ENV NV_LIBNCCL_PACKAGE_VERSION 2.21.5-1
ENV NV_LIBNCCL_VERSION 2.21.5
ENV NCCL_VERSION 2.21.5
ENV NV_LIBNCCL_PACKAGE ${NV_LIBNCCL_PACKAGE_NAME}-${NV_LIBNCCL_PACKAGE_VERSION}+cuda12.4

RUN yum install -y \
    cuda-libraries-12-4-${NV_CUDA_LIB_VERSION} \
    cuda-nvtx-12-4-${NV_NVTX_VERSION} \
    ${NV_LIBNPP_PACKAGE} \
    libcublas-12-4-${NV_LIBCUBLAS_VERSION} \
    ${NV_LIBNCCL_PACKAGE} \
    && yum clean all \
    && rm -rf /var/cache/yum/*

# Set this flag so that libraries can find the location of CUDA
ENV XLA_FLAGS=--xla_gpu_cuda_data_dir=/usr/local/cuda

# Install CUDA devel from:
# https://gitlab.com/nvidia/container-images/cuda/-/blob/master/dist/12.4.1/ubi9/devel/Dockerfile
ENV NV_CUDA_LIB_VERSION 12.4.1-1
ENV NV_NVPROF_VERSION 12.4.127-1
ENV NV_NVPROF_DEV_PACKAGE cuda-nvprof-12-4-${NV_NVPROF_VERSION}
ENV NV_CUDA_CUDART_DEV_VERSION 12.4.127-1
ENV NV_NVML_DEV_VERSION 12.4.127-1
ENV NV_LIBCUBLAS_DEV_VERSION 12.4.5.8-1
ENV NV_LIBNPP_DEV_VERSION 12.2.5.30-1
ENV NV_LIBNPP_DEV_PACKAGE libnpp-devel-12-4-${NV_LIBNPP_DEV_VERSION}
ENV NV_LIBNCCL_DEV_PACKAGE_NAME libnccl-devel
ENV NV_LIBNCCL_DEV_PACKAGE_VERSION 2.21.5-1
ENV NCCL_VERSION 2.21.5
ENV NV_LIBNCCL_DEV_PACKAGE ${NV_LIBNCCL_DEV_PACKAGE_NAME}-${NV_LIBNCCL_DEV_PACKAGE_VERSION}+cuda12.4
ENV NV_CUDA_NSIGHT_COMPUTE_VERSION 12.4.1-1
ENV NV_CUDA_NSIGHT_COMPUTE_DEV_PACKAGE cuda-nsight-compute-12-4-${NV_CUDA_NSIGHT_COMPUTE_VERSION}

RUN yum install -y \
    make \
    findutils \
    cuda-command-line-tools-12-4-${NV_CUDA_LIB_VERSION} \
    cuda-libraries-devel-12-4-${NV_CUDA_LIB_VERSION} \
    cuda-minimal-build-12-4-${NV_CUDA_LIB_VERSION} \
    cuda-cudart-devel-12-4-${NV_CUDA_CUDART_DEV_VERSION} \
    ${NV_NVPROF_DEV_PACKAGE} \
    cuda-nvml-devel-12-4-${NV_NVML_DEV_VERSION} \
    libcublas-devel-12-4-${NV_LIBCUBLAS_DEV_VERSION} \
    ${NV_LIBNPP_DEV_PACKAGE} \
    ${NV_LIBNCCL_DEV_PACKAGE} \
    ${NV_CUDA_NSIGHT_COMPUTE_DEV_PACKAGE} \
    && yum clean all \
    && rm -rf /var/cache/yum/*

ENV LIBRARY_PATH /usr/local/cuda/lib64/stubs

# Install CUDA devel cudnn8 from:
# hhttps://gitlab.com/nvidia/container-images/cuda/-/blob/master/dist/12.4.1/ubi9/devel/cudnn/Dockerfile
ENV NV_CUDNN_VERSION 9.1.0.70-1
ENV NV_CUDNN_PACKAGE libcudnn9-cuda-12-${NV_CUDNN_VERSION}
ENV NV_CUDNN_PACKAGE_DEV libcudnn9-devel-cuda-12-${NV_CUDNN_VERSION}

LABEL com.nvidia.cudnn.version="${NV_CUDNN_VERSION}"

RUN yum install -y \
    ${NV_CUDNN_PACKAGE} \
    ${NV_CUDNN_PACKAGE_DEV} \
    && yum clean all \
    && rm -rf /var/cache/yum/*

# Install CUDA toolkit 12.4
RUN yum -y install cuda-toolkit-12-4 && \
    yum -y clean all --enablerepo="*"

# Set this flag so that libraries can find the location of CUDA
ENV XLA_FLAGS=--xla_gpu_cuda_data_dir=/usr/local/cuda

# Unregister the system
RUN subscription-manager remove --all && subscription-manager unregister && subscription-manager clean

# Restore notebook user workspace
USER 1001
WORKDIR /opt/app-root/src
