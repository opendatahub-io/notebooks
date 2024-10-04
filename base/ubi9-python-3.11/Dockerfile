FROM registry.access.redhat.com/ubi9/ubi:latest

# perform the setup that python s2i image used to do for us
#  but this way it uses a lot less disk space (hundreds of megabytes less)
ENV APP_ROOT="/opt/app-root"
ENV HOME="${APP_ROOT}/src"
ENV VIRTUAL_ENV="${APP_ROOT}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV PYTHON_VERSION=3.11
ENV PIP_NO_CACHE_DIR=off
RUN mkdir --parents "${HOME}" && chmod --recursive 0771 ${APP_ROOT} && chown --recursive 1001:0 ${APP_ROOT} && \
    useradd --uid 1001 --gid 0 --no-create-home --home-dir "${HOME}" \
      --comment "Default Application User" --shell /bin/bash default && \
    dnf install -y python${PYTHON_VERSION}-pip && dnf clean all && rm -rf /var/cache/yum/*
COPY --from=quay.io/sclorg/s2i-core-c9s:latest /usr/bin/fix-permissions /usr/bin/rpm-file-permissions /usr/bin/

USER 1001
RUN python${PYTHON_VERSION} -m venv "${VIRTUAL_ENV}"

ARG SOURCE_CODE=base/ubi9-python-3.11

LABEL name="odh-notebook-base-ubi9-python-3.11" \
      summary="Python 3.11 base image for ODH notebooks" \
      description="Base Python 3.11 builder image based on UBI9 for ODH notebooks" \
      io.k8s.display-name="Python 3.11 base image for ODH notebooks" \
      io.k8s.description="Base Python 3.11 builder image based on UBI9 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/base/ubi9-python-3.11" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:base-ubi9-python-3.11"

WORKDIR /opt/app-root/bin

# Install micropipenv to deploy packages from Pipfile.lock
RUN pip install --no-cache-dir -U "micropipenv[toml]"

# Install Python dependencies from Pipfile.lock file
COPY ${SOURCE_CODE}/Pipfile.lock ./

RUN echo "Installing software and packages" && micropipenv install && rm -f ./Pipfile.lock

# OS Packages needs to be installed as root
USER root

# Install usefull OS packages
RUN dnf install -y \
      mesa-libGL \
      patch \
      wget \
    && dnf clean all && rm -rf /var/cache/yum

# Other apps and tools installed as default user
USER 1001

# Install the oc client
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python${PYTHON_VERSION}/site-packages && \
      fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
