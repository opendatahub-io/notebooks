FROM quay.io/sclorg/python-39-c9s:c9s

LABEL name="odh-notebook-base-centos-stream9-python-3.9" \
      summary="Python 3.9 CentOS Stream 9 base image for ODH notebooks" \
      description="Base Python 3.9 builder image based on CentOS Stream 9 for ODH notebooks" \
      io.k9s.display-name="Python 3.9 c9s base image for ODH notebooks" \
      io.k9s.description="Base Python 3.9 builder image based on C9S for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/base/c9s-python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:base-c9s-python-3.9"

WORKDIR /opt/app-root/bin

# Install micropipenv to deploy packages from Pipfile.lock
RUN pip install -U "micropipenv[toml]"

# Install Python dependencies from Pipfile.lock file
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock && \
    # Install the oc client \
    curl -L https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
