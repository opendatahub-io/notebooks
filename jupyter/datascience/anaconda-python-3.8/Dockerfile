ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="s2i-minimal-notebook-anaconda:latest" \
    summary="Minimal Jupyter Notebook Source-to-Image for Python 3.8 applications. Uses Anaconda CE instead of pip." \
    description="Notebook image based on Anaconda CE Python.These images can be used in OpenDatahub JupterHub." \
    io.k8s.description="Notebook image based on Anaconda CE Python.These images can be used in OpenDatahub JupterHub." \
    io.k8s.display-name="Anaconda s2i-minimal-notebook, python38" \
    io.openshift.expose-services="8888:http" \
    io.openshift.tags="python,python38,python-38,anaconda-python38" \
    authoritative-source-url="https://quay.io/modh/s2i-minimal-notebook-anaconda" \
    io.openshift.s2i.build.commit.ref="master" \
    io.openshift.s2i.build.source-location="https://github.com/red-hat-data-services/s2i-minimal-notebook-anaconda" \
    io.openshift.s2i.build.image="quay.io/modh/s2i-minimal-notebook-anaconda:latest"

ENV JUPYTER_ENABLE_LAB="1"
USER root

# User the NodeJS from Anaconda > 12.0
RUN yum remove -y nodejs

# Copying in override assemble/run scripts
COPY .s2i/bin /tmp/scripts
# Copying in source code
COPY . /tmp/src
# Change file ownership to the assemble user. Builder image must support chown command.
RUN chown -R 1001:0 /tmp/scripts /tmp/src
USER 1001
RUN /tmp/scripts/assemble

USER root
RUN mkdir /etc/conda
COPY condarc /etc/conda/condarc

USER 1001
CMD /tmp/scripts/run