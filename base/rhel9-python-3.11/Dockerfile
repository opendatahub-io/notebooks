FROM registry.redhat.io/rhel9/python-311:latest

LABEL name="rhoai-notebook-base-rhel9-python-3.11" \
      summary="Python 3.11 Red Hat Enterprise Linux 9 base image for RHOAI notebooks" \
      description="Base Python 3.11 builder image based on Red Hat Enterprise Linux 9 for RHOAI notebooks" \
      io.k9s.display-name="Python 3.11 RHEL9 base image for RHOAI notebooks" \
      io.k9s.description="Base Python 3.11 builder image based on RHEL9 for RHOAI notebooks" \
      authoritative-source-url="https://github.com/red-hat-data-services/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/red-hat-data-services/notebooks/tree/main/base/rhel9-python-3.11" \
      io.openshift.build.image="quay.io/modh/odh-base-rhel9"

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
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
      fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
