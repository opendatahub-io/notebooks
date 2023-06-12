ARG BASE_IMAGE
FROM ${BASE_IMAGE}

LABEL name="jupyter-datascience-anaconda-python-3.8:latest" \
    summary="Minimal Jupyter Notebook Source-to-Image for Python 3.8 applications. Uses Anaconda CE instead of pip." \
    description="Notebook image based on Anaconda CE Python.These images can be used in OpenDatahub JupterHub." \
    io.k8s.description="Notebook image based on Anaconda CE Python.These images can be used in OpenDatahub JupterHub." \
    io.k8s.display-name="Anaconda s2i-minimal-notebook, python38" \
    io.openshift.expose-services="8888:http" \
    io.openshift.tags="python,python38,python-38,anaconda-python38" \
    authoritative-source-url="https://quay.io//opendatahub/workbench-images:jupyter-datascience-anaconda-python-3.8" \
    io.openshift.s2i.build.commit.ref="main" \
    io.openshift.s2i.build.source-location="https://github.com/opendatahub-io/notebooks/jupyter/datascience/anaconda-python-3.8" \
    io.openshift.s2i.build.image="quay.io/repository/opendatahub/workbench-images:jupyter-datascience-anaconda-python-3.8"

ENV JUPYTER_ENABLE_LAB="1"
USER root

# Use the NodeJS from Anaconda > 12.0
RUN yum remove -y nodejs

WORKDIR /opt/app-root/bin

COPY utils utils/

# Install Python packages and Jupyterlab extensions from conda environment file
COPY environment.yml start-notebook.sh ./
# Copy Elyra setup to utils so that it's sourced at startup
COPY jupyter_elyra_config.py setup-elyra.sh pipeline-flow.svg ./utils/

RUN echo "Installing softwares and packages" && \
    /opt/anaconda3/bin/conda env update -p "${APP_ROOT}" --file environment.yml && \
    rm -f ./environment.yml && \
    # setup path for runtime configuration \
    mkdir /opt/app-root/runtimes && \
    # switch to Data Science Pipeline \
    cp utils/pipeline-flow.svg /opt/app-root/lib/python3.8/site-packages/elyra/static/icons/kubeflow.svg && \
    sed -i "s/Kubeflow Pipelines/Data Science/g" /opt/app-root/lib/python3.8/site-packages/elyra/pipeline/runtime_type.py && \
    sed -i "s/Kubeflow Pipelines/Data Science Pipelines/g" /opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/kfp.json && \
    sed -i "s/\"default\": \"Argo\",/\"default\": \"Tekton\",/g" /opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/kfp.json && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y \
    sed -i -e "s/Python.*/$(python --version)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
    # Remove default Elyra runtime-images \
    rm /opt/app-root/share/jupyter/metadata/runtime-images/*.json && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.8/site-packages && \
    fix-permissions /opt/app-root -P

# Copy Elyra runtime-images definitions and set the version
COPY runtime-images/ /opt/app-root/share/jupyter/metadata/runtime-images/

USER root
RUN mkdir /etc/conda
COPY condarc /etc/conda/condarc

USER 1001

ENTRYPOINT ["start-notebook.sh"]
