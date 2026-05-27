ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER 0

ARG APP_ROOT=/opt/app-root

# Override pip/uv config to use PyPI instead of AIPCC index
RUN printf '[global]\nindex-url = https://pypi.org/simple/\n' > ${APP_ROOT}/pip.conf \
 && printf 'index-url = "https://pypi.org/simple/"\n' > ${APP_ROOT}/uv.toml

# Install JupyterLab and friends from PyPI (nonhermetic -- downloads at build time)
RUN pip install --no-cache-dir \
    jupyterlab \
    jupyter-server \
    jupyter-server-proxy \
    jupyter-server-terminals \
    jupyterlab-git \
    nbdime \
    nbgitpuller

COPY jupyter/minimal/ubi9-python-3.12/start-notebook.sh ${APP_ROOT}/bin/
COPY jupyter/utils/ ${APP_ROOT}/bin/utils/

RUN mkdir -p ${APP_ROOT}/etc/jupyter \
 && cp ${APP_ROOT}/bin/utils/jupyter_server_config.py ${APP_ROOT}/etc/jupyter/ \
 && chmod +x ${APP_ROOT}/bin/start-notebook.sh \
 && fix-permissions ${APP_ROOT} -P

USER 1001
WORKDIR ${APP_ROOT}/src

ENTRYPOINT ["start-notebook.sh"]
