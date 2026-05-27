ARG BASE_IMAGE=registry.access.redhat.com/ubi9/python-312:latest
FROM ${BASE_IMAGE}

USER 0

# Override pip/uv config to use PyPI instead of AIPCC index
RUN printf '[global]\nindex-url = https://pypi.org/simple/\n' > /opt/app-root/pip.conf \
 && printf 'index-url = "https://pypi.org/simple/"\n' > /opt/app-root/uv.toml

ENV PIP_CONFIG_FILE=/opt/app-root/pip.conf

# libatomic: required by ROCm PyTorch (user pip installs torch with rocm index)
RUN dnf install -y libatomic && dnf clean all

# Install JupyterLab and friends from PyPI (nonhermetic -- downloads at build time)
RUN pip install --no-cache-dir \
    jupyterlab \
    jupyter-server \
    jupyter-server-proxy \
    jupyter-server-terminals \
    jupyterlab-git \
    nbdime \
    nbgitpuller

COPY jupyter/minimal/ubi9-python-3.12/start-notebook.sh /opt/app-root/bin/
COPY jupyter/utils/ /opt/app-root/bin/utils/

RUN mkdir -p /opt/app-root/etc/jupyter \
 && cp /opt/app-root/bin/utils/jupyter_server_config.py /opt/app-root/etc/jupyter/ \
 && chmod +x /opt/app-root/bin/start-notebook.sh \
 && fix-permissions /opt/app-root -P

USER 1001
WORKDIR /opt/app-root/src

ENTRYPOINT ["start-notebook.sh"]
