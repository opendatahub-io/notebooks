########
# base #
########

# https://catalog.redhat.com/software/containers/registry/registry.access.redhat.com/repository/ubi9/python-311
FROM registry.access.redhat.com/ubi9/python-311:latest
# Subsequent code may leverages the folloving definitions from the base image:
# ENV APP_ROOT=/opt/app-root
# ENV HOME="${APP_ROOT}/src"
# ENV PYTHON_VERSION=3.11
# ENV PYTHONUNBUFFERED=1
# ENV PYTHONIOENCODING=UTF-8
# ENV PIP_NO_CACHE_DIR=off
# ENV BASH_ENV="${APP_ROOT}/bin/activate"
# ENV ENV="${APP_ROOT}/bin/activate"

# OS packages needs to be installed as root
USER root

# Install useful OS packages
RUN dnf install -y mesa-libGL skopeo && dnf clean all && rm -rf /var/cache/yum

# Other apps and tools shall be installed as default user
# - Kuberneres requires using numeric IDs for the final USER command
# - Openshift's SCC restricted-v2 policy runs images under random UID and GID of 0
USER 1001:0
WORKDIR /opt/app-root

ARG JUPYTER_REUSABLE_UTILS=jupyter/utils
ARG MINIMAL_SOURCE_CODE=jupyter/minimal/ubi9-python-3.11
ARG DATASCIENCE_SOURCE_CODE=jupyter/datascience/ubi9-python-3.11

# Emplace and activate our entrypoint script
COPY ${MINIMAL_SOURCE_CODE}/start-notebook.sh /opt/app-root/bin/
ENTRYPOINT ["/opt/app-root/bin/start-notebook.sh"]
# Copy JupyterLab config from utils directory
COPY ${JUPYTER_REUSABLE_UTILS} /opt/app-root/bin/utils/
# Copy Elyra setup script and various utils where start-notebook.sh expects it
COPY ${DATASCIENCE_SOURCE_CODE}/setup-elyra.sh ${DATASCIENCE_SOURCE_CODE}/utils /opt/app-root/bin/utils/

# Install Python packages and Jupyterlab extensions
# https://www.docker.com/blog/introduction-to-heredocs-in-dockerfiles/

COPY <<EOF requirements.txt
--index-url https://pypi.org/simple

# JupyterLab
jupyterlab==4.2.7
jupyter-bokeh~=4.0.5
jupyter-server~=2.15.0
jupyter-server-proxy~=4.4.0
jupyter-server-terminals~=0.5.3
jupyterlab-git~=0.50.1
jupyterlab-lsp~=5.1.0
jupyterlab-widgets~=3.0.13
jupyter-resource-usage~=1.1.1
nbdime~=4.0.2
nbgitpuller~=1.2.2

# Elyra
odh-elyra==4.2.1
kfp~=2.12.1

# Miscellaneous datascience packages
matplotlib~=3.10.1
numpy~=2.2.3
# ...
EOF

RUN echo "Installing software and packages" && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -f ./Pipfile.lock && \
    # Prepare directories for elyra runtime configuration
    mkdir /opt/app-root/runtimes && \
    mkdir /opt/app-root/pipeline-runtimes && \
    # Remove default Elyra runtime-images
    rm /opt/app-root/share/jupyter/metadata/runtime-images/*.json && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y
    sed -i -e "s/Python.*/$(python --version | cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Copy jupyter configuration
    cp /opt/app-root/bin/utils/jupyter_server_config.py /opt/app-root/etc/jupyter && \
    # Disable announcement plugin of jupyterlab
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    # Fix permissions to support pip in Openshift environments
    chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
    fix-permissions /opt/app-root -P

# Switch dir to $HOME
WORKDIR /opt/app-root/src
