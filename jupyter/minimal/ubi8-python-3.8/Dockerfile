ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-minimal-ubi8-python-3.8" \
    summary="Minimal Jupyter notebook image for ODH notebooks" \
    description="Minimal Jupyter notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    io.k8s.display-name="Minimal Jupyter notebook image for ODH notebooks" \
    io.k8s.description="Minimal Jupyter notebook image with base Python 3.8 builder image based on UBI8 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/minimal/ubi8-python-3.8" \
    io.openshift.build.image="quay.io/opendatahub/notebooks:jupyter-minimal-ubi8-python-3.8"


WORKDIR /opt/app-root/bin

COPY requirements.txt start-notebook.sh ./

RUN python -m pip install -r requirements.txt && rm -f requirements.txt

WORKDIR /opt/app-root/src

ENTRYPOINT ["start-notebook.sh"]
