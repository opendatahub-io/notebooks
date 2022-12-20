ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-minimal-ubi9-python-3.9" \
    summary="Minimal Jupyter notebook image for ODH notebooks" \
    description="Minimal Jupyter notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k9s.display-name="Minimal Jupyter notebook image for ODH notebooks" \
    io.k9s.description="Minimal Jupyter notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/minimal/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/notebooks:jupyter-minimal-ubi9-python-3.9"

WORKDIR /opt/app-root/bin

COPY utils utils/
COPY requirements.txt start-notebook.sh ./

RUN python -m pip install -r requirements.txt && \
      rm -f requirements.txt

# Fix permissions to support pip in Openshift environments
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
      fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src

RUN sed -i -e "s/Python.*/$(python --version)\",/" \
      /opt/app-root/share/jupyter/kernels/python3/kernel.json

ENTRYPOINT ["start-notebook.sh"]

