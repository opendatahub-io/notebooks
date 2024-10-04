ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="odh-notebook-jupyter-minimal-ubi9-python-3.11" \
    summary="Minimal Jupyter notebook image for ODH notebooks" \
    description="Minimal Jupyter notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Minimal Jupyter notebook image for ODH notebooks" \
    io.k8s.description="Minimal Jupyter notebook image with base Python 3.11 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/minimal/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:jupyter-minimal-ubi9-python-3.11"

RUN python${PYTHON_VERSION} -m venv /opt/app-root/opt
WORKDIR /opt/app-root/opt
COPY pyproject.toml poetry.lock ./
RUN echo "Installing jupyterlab" && \
    export VIRTUAL_ENV=/opt/app-root/opt && \
    (source $VIRTUAL_ENV/bin/activate && micropipenv install --method=poetry) && \
    rm -f ./pyproject.toml ./poetry.lock && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/opt/lib/python${PYTHON_VERSION}/site-packages && \
    fix-permissions /opt/app-root -P
USER root
RUN ln -s /opt/app-root/opt/bin/jupyter /usr/local/bin/jupyter
RUN ln -s /opt/app-root/opt/bin/jupyter-lab /usr/local/bin/jupyter-lab
RUN ln -s /opt/app-root/opt/bin/jupyter-labextension /usr/local/bin/jupyter-labextension
USER default

WORKDIR /opt/app-root/bin

COPY utils utils/

COPY Pipfile.lock start-notebook.sh ./

# Install Python dependencies from Pipfile.lock file
RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
    fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src

# Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
RUN python${PYTHON_VERSION} -m ipykernel install --prefix /opt/app-root/opt --name python3 --display-name "$(python -c 'import sys; major, minor, *_ = sys.version_info; print(f"Python {major}.{minor}")')"

ENTRYPOINT ["start-notebook.sh"]

