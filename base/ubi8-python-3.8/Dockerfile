FROM registry.access.redhat.com/ubi8/python-38:latest

LABEL name="odh-notebook-base-ubi8-python-3.8" \
      summary="Python 3.8 base image for ODH notebooks" \
      description="Base Python 3.8 builder image based on UBI8 for ODH notebooks" \
      io.k8s.display-name="Python 3.8 base image for ODH notebooks" \
      io.k8s.description="Base Python 3.8 builder image based on UBI8 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/base/ubi8-python-3.8" \
      io.openshift.build.image="quay.io/opendatahub/notebooks:base-ubi8-python-3.8"

WORKDIR /opt/app-root/bin

COPY requirements.txt ./

# Install Python dependencies from requirements.txt file
RUN python -m pip install -r requirements.txt && \
      rm -f requirements.txt

# Install the oc client
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz

WORKDIR /opt/app-root/src
