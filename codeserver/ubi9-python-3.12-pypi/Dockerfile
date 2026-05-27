ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER 0

ARG APP_ROOT=/opt/app-root

# Override pip/uv config to use PyPI instead of AIPCC index
RUN printf '[global]\nindex-url = https://pypi.org/simple/\n' > ${APP_ROOT}/pip.conf \
 && printf 'index-url = "https://pypi.org/simple/"\n' > ${APP_ROOT}/uv.toml

# Install code-server from upstream GitHub RPM (nonhermetic)
ARG CODESERVER_VERSION=4.106.3
ARG TARGETARCH=amd64
RUN curl -fOL https://github.com/coder/code-server/releases/download/v${CODESERVER_VERSION}/code-server-${CODESERVER_VERSION}-${TARGETARCH}.rpm \
 && rpm -U code-server-${CODESERVER_VERSION}-${TARGETARCH}.rpm \
 && rm -f code-server-${CODESERVER_VERSION}-${TARGETARCH}.rpm

# Install nginx for reverse proxy (handles NB_PREFIX path rewriting for OpenShift)
RUN dnf install -y nginx \
 && dnf clean all

# Install Python kernel support for VS Code
RUN pip install --no-cache-dir jupyter ipykernel

# Create nginx config template that rewrites NB_PREFIX to code-server on 8787
RUN mkdir -p /opt/app-root/etc/nginx.default.d
COPY codeserver/ubi9-python-3.12-pypi/start-codeserver.sh ${APP_ROOT}/bin/

# Ensure writable dirs
RUN mkdir -p ${APP_ROOT}/src/.local/share/code-server \
    /var/log/nginx /var/lib/nginx /run \
 && chown -R 1001:0 /var/log/nginx /var/lib/nginx /run /etc/nginx \
 && chmod -R ug+rwX /var/log/nginx /var/lib/nginx /run /etc/nginx \
 && fix-permissions ${APP_ROOT} -P

USER 1001
WORKDIR ${APP_ROOT}/src

EXPOSE 8888

CMD ["/opt/app-root/bin/start-codeserver.sh"]
