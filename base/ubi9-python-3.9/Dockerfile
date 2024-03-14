FROM registry.access.redhat.com/ubi9/python-39:latest

LABEL name="odh-notebook-base-ubi9-python-3.9" \
      summary="Python 3.9 base image for ODH notebooks" \
      description="Base Python 3.9 builder image based on UBI9 for ODH notebooks" \
      io.k8s.display-name="Python 3.9 base image for ODH notebooks" \
      io.k8s.description="Base Python 3.9 builder image based on UBI9 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/base/ubi9-python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:base-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

# Install micropipenv to deploy packages from Pipfile.lock
RUN pip install --no-cache-dir -U "micropipenv[toml]"

# Install Python dependencies from Pipfile.lock file
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# OS Packages needs to be installed as root
USER root

# Install usefull OS packages
RUN dnf install -y mesa-libGL && dnf clean all && rm -rf /var/cache/yum

# Other apps and tools installed as default user
USER 1001

# Install the oc client
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
      fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
