ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG SOURCE_CODE=jupyter/intel/tensorflow/ubi9-python-3.9

LABEL name="odh-notebook-jupyter-intel-tensorflow-ubi9-python-3.9" \
    summary="Jupyter Intel® optimized TensorFlow notebook image for ODH notebooks." \
    description="Jupyter Intel® TensorFlow notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    io.k8s.display-name="Jupyter Intel® optimized TensorFlow notebook image for ODH notebooks." \
    io.k8s.description="Jupyter Intel® optimized TensorFlow notebook image with base Python 3.9 builder image based on UBI9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/jupyter/intel/tensorflow/ubi9-python-3.9" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:jupyter-intel-tensorflow-ubi9-python-3.9"

USER root

ARG ONEAPI_VERSION=2024.0
COPY ${SOURCE_CODE}/oneAPI.repo /etc/yum.repos.d/oneAPI.repo

RUN dnf update -y && \
    dnf install -y intel-oneapi-compiler-dpcpp-cpp-runtime-${ONEAPI_VERSION} \
        intel-oneapi-mkl-${ONEAPI_VERSION} \
        intel-oneapi-dnnl-${ONEAPI_VERSION} && \
    dnf clean all -y && \
    rm -rf /var/cache/dnf/* && \
    rm /etc/yum.repos.d/oneAPI.repo

USER 1001

WORKDIR /opt/app-root/bin

# Install Python packages and Jupyterlab extensions from Pipfile.lock
COPY ${SOURCE_CODE}/Pipfile.lock.gpu Pipfile.lock

RUN unlink /opt/app-root/lib64 && \
    cp -r /opt/app-root/lib /opt/app-root/lib64 && \
    echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

#Replacing kernel manually with oneapi variable setting script
COPY --chown=1001:0 ${SOURCE_CODE}/start-kernel /opt/app-root/bin/start-kernel
COPY --chown=1001:0 ${SOURCE_CODE}/kernel-gpu.json /opt/app-root/share/jupyter/kernels/python3/kernel.json
COPY --chown=1001:0 ${SOURCE_CODE}/start-notebook.sh /opt/app-root/bin
COPY --chown=1001:0 ${SOURCE_CODE}/builder /opt/app-root/builder
COPY --chown=1001:0 ${SOURCE_CODE}/utils /opt/app-root/bin/utils

#CPU env
ENV CPU_ENV=/opt/app-root-cpu
ENV GPU_ENV=/opt/app-root
COPY --chown=1001:0 ${SOURCE_CODE}/Pipfile.lock.cpu ${CPU_ENV}/Pipfile.lock

WORKDIR ${CPU_ENV}

RUN python3.9 -m venv ${CPU_ENV} && \
    chown -R 1001:0 ${CPU_ENV} && \
    fix-permissions ${CPU_ENV} -P && \
    unlink ${CPU_ENV}/lib64 && \
    cp -r ${CPU_ENV}/lib ${CPU_ENV}/lib64 && \
    source ${CPU_ENV}/bin/activate && \
    pip install --no-cache-dir -U "micropipenv[toml]" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    python -m ipykernel install --prefix=/opt/app-root --name 'tensorflow-cpu' --display-name='tensorflow-cpu' && \
    # Disable announcement plugin of jupyterlab \
    jupyter labextension disable "@jupyterlab/apputils-extension:announcements" && \
    chmod -R g+w ${CPU_ENV}/lib/python3.9/site-packages && \
    fix-permissions ${CPU_ENV} -P && \
    chmod -R g+w /opt/app-root/src && \
    # Apply JupyterLab addons
    /opt/app-root/bin/utils/addons/apply.sh

COPY --chown=1001:0 ${SOURCE_CODE}/kernel-cpu.json /opt/app-root/share/jupyter/kernels/tensorflow-cpu/kernel.json

WORKDIR /opt/app-root/src

ENV JUPYTER_PRELOAD_REPOS="https://github.com/IntelAI/oneAPI-samples"
ENV REPO_BRANCH="main"

ENTRYPOINT ["bash", "-c", "/opt/app-root/builder/run"]
