# Reference:
#  - https://vault.habana.ai/ui/repos/tree/General/gaudi-docker/1.17.1/rhel9.4/habanalabs/pytorch-installer-2.3.1/1.17.1-40
FROM vault.habana.ai/gaudi-docker/1.17.1/rhel9.4/habanalabs/pytorch-installer-2.3.1:1.17.1-40 as base

LABEL name="odh-notebook-habana-jupyter-1.17.1-ubi9-python-3.11" \
    summary="Jupyter HabanaAI 1.17.1 notebook image for ODH notebooks" \
    description="Jupyter HabanaAI 1.17.1 notebook image with base Python 3.11 builder image based on ubi9 for ODH notebooks" \
    io.k8s.display-name="Jupyter HabanaAI 1.17.1 notebook image for ODH notebooks" \
    io.k8s.description="Jupyter HabanaAI 1.17.1 notebook image with base Python 3.11 builder image based on ubi9 for ODH notebooks" \
    authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
    io.openshift.build.commit.ref="main" \
    io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/habana/1.17.1/ubi9-python-3.11" \
    io.openshift.build.image="quay.io/opendatahub/workbench-images:habana-jupyter-1.17.1-ubi9-python-3.11"

COPY --from=registry.access.redhat.com/ubi9/python-39:latest /usr/bin/fix-permissions /usr/bin
COPY --from=registry.access.redhat.com/ubi9/python-39:latest /usr/bin/rpm-file-permissions /usr/bin

ENV PATH=/opt/app-root/src/bin:/opt/app-root/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    APP_ROOT="/opt/app-root"

ENV HOME="${APP_ROOT}/src"

WORKDIR ${HOME}

RUN mkdir -p ${APP_ROOT}/src && \
    rpm-file-permissions && \
    useradd -u 1001 -r -g 0 -d ${HOME} -c "Default Application User" default && \
    chown -R 1001:0 ${APP_ROOT}

FROM base as notebook-base

ENV PYTHON_VERSION=3.11 \
    PATH=$HOME/.local/bin/:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off

RUN python3.11 -m venv --system-site-packages ${APP_ROOT} && \
    chown -R 1001:0 ${APP_ROOT} && \
    fix-permissions ${APP_ROOT} -P && \
    rpm-file-permissions && \
    echo "unset BASH_ENV PROMPT_COMMAND ENV" >> ${APP_ROOT}/bin/activate

ENV BASH_ENV="${APP_ROOT}/bin/activate" \
    ENV="${APP_ROOT}/bin/activate" \
    PROMPT_COMMAND=". ${APP_ROOT}/bin/activate"

# Apparently the following is needed due to training options.
# More information can be seen in the official documentation:
#   - https://instructlab.readthedocs.io/latest/habana-gaudi.html#install-and-run-instructlab-with-intel-gaudi
ENV TSAN_OPTIONS='ignore_noninstrumented_modules=1'

WORKDIR /opt/app-root/bin

# Install micropipenv to deploy packages from Pipfile.lock
RUN pip install --no-cache-dir -U "micropipenv[toml]" && \
chmod -R g+w /opt/app-root/lib/python3.11/site-packages && \
fix-permissions /opt/app-root -P

# Install Python dependencies from Pipfile.lock file
COPY Pipfile.lock ./

RUN echo "Installing softwares and packages" && micropipenv install && rm -f ./Pipfile.lock

# OS Packages needs to be installed as root
USER root

# Install usefull OS packages
RUN dnf install -y mesa-libGL && dnf clean all && rm -rf /var/cache/yum

# Install the oc client
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz \
-o /tmp/openshift-client-linux.tar.gz && \
tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
rm -f /tmp/openshift-client-linux.tar.gz

# Other apps and tools installed as default user
USER 1001

WORKDIR /opt/app-root/src
