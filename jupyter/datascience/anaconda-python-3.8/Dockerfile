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
RUN yum remove -y nodejs && \
    yum install -y jq

# Install usefull OS packages
RUN dnf install -y jq unixODBC git-lfs libsndfile

# Disable announcement plugin of jupyterlab
RUN jupyter labextension disable "@jupyterlab/apputils-extension:announcements"

# Install MongoDB Client, We need a special repo for MongoDB as they do their own distribution
COPY mongodb-org-6.0.repo-x86_64 /etc/yum.repos.d/mongodb-org-6.0.repo
RUN dnf install -y mongocli

# Install MSSQL Client, We need a special repo for MSSQL as they do their own distribution
COPY mssql-2022.repo-x86_64 /etc/yum.repos.d/mssql-2022.repo
RUN ACCEPT_EULA=Y dnf install -y mssql-tools18 unixODBC-devel
ENV PATH="$PATH:/opt/mssql-tools18/bin"

# Other apps and tools installed as default user
USER 1001

WORKDIR /opt/app-root/bin

COPY utils ./utils/

# Install Python packages and Jupyterlab extensions from conda environment file
COPY environment.yml start-notebook.sh ./
# Copy Elyra setup to utils so that it's sourced at startup
COPY setup-elyra.sh ./utils/

RUN echo "Installing softwares and packages" && \
    /opt/anaconda3/bin/conda env create --file environment.yml -p "${APP_ROOT}" && \
    rm -f ./environment.yml && \
    # setup path for runtime configuration \
    mkdir /opt/app-root/runtimes && \
    # switch to Data Science Pipeline \
    cp utils/pipeline-flow.svg /opt/app-root/lib/python3.8/site-packages/elyra/static/icons/kubeflow.svg && \
    sed -i "s/Kubeflow Pipelines/Data Science/g" /opt/app-root/lib/python3.8/site-packages/elyra/pipeline/runtime_type.py && \
    sed -i "s/Kubeflow Pipelines/Data Science Pipelines/g" /opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/kfp.json && \
    sed -i "s/kubeflow-service/data-science-pipeline-service/g" /opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/kfp.json && \
    sed -i "s/\"default\": \"Argo\",/\"default\": \"Tekton\",/g" /opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/kfp.json && \
    # Workaround for passing ssl_sa_cert
    patch /opt/app-root/lib/python3.8/site-packages/elyra/pipeline/kfp/kfp_authentication.py -i utils/kfp_authentication.patch && \
    patch /opt/app-root/lib/python3.8/site-packages/elyra/pipeline/kfp/processor_kfp.py -i utils/processor_kfp.patch && \
    # switch to Data Science Pipeline in component catalog \
    DIR_COMPONENT="/opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/local-directory-catalog.json" && \
    FILE_COMPONENT="/opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/local-file-catalog.json" && \
    URL_COMPONENT="/opt/app-root/lib/python3.8/site-packages/elyra/metadata/schemas/url-catalog.json" && \
    tmp=$(mktemp) && \
    jq '.properties.metadata.properties.runtime_type = input' $DIR_COMPONENT utils/component_runtime.json > "$tmp" && mv "$tmp" $DIR_COMPONENT && \
    jq '.properties.metadata.properties.runtime_type = input' $FILE_COMPONENT utils/component_runtime.json > "$tmp" && mv "$tmp" $FILE_COMPONENT && \
    jq '.properties.metadata.properties.runtime_type = input' $URL_COMPONENT utils/component_runtime.json > "$tmp" && mv "$tmp" $URL_COMPONENT && \
    sed -i "s/metadata.metadata.runtime_type/\"DATA_SCIENCE_PIPELINES\"/g" /opt/app-root/share/jupyter/labextensions/@elyra/pipeline-editor-extension/static/lib_index_js.*.js && \
    # Explicitly enable jupyterlab_s3_browser plugin \
    jupyter serverextension enable --py jupyterlab_s3_browser && \
    # Remove Elyra logo from JupyterLab because this is not a pure Elyra image \
    sed -i 's/widget\.id === \x27jp-MainLogo\x27/widget\.id === \x27jp-MainLogo\x27 \&\& false/' /opt/app-root/share/jupyter/labextensions/@elyra/theme-extension/static/lib_index_js.*.js && \
    # Replace Notebook's launcher, "(ipykernel)" with Python's version 3.x.y \
    sed -i -e "s/Python.*/$(python --version| cut -d '.' -f-2)\",/" /opt/app-root/share/jupyter/kernels/python3/kernel.json && \
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
