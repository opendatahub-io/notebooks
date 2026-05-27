ARG BASE_IMAGE=registry.access.redhat.com/ubi9/python-312:latest
FROM ${BASE_IMAGE}

USER 0

# Override pip/uv config to use PyPI instead of AIPCC index
RUN printf '[global]\nindex-url = https://pypi.org/simple/\n' > /opt/app-root/pip.conf \
 && printf 'index-url = "https://pypi.org/simple/"\n' > /opt/app-root/uv.toml

ENV PIP_CONFIG_FILE=/opt/app-root/pip.conf

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

COPY codeserver/ubi9-python-3.12-pypi/start-codeserver.sh /opt/app-root/bin/

# Ensure writable dirs
RUN mkdir -p /opt/app-root/src/.local/share/code-server \
    /var/log/nginx /var/lib/nginx /run \
 && chown -R 1001:0 /var/log/nginx /var/lib/nginx /run /etc/nginx \
 && chmod -R ug+rwX /var/log/nginx /var/lib/nginx /run /etc/nginx \
 && chmod +x /opt/app-root/bin/start-codeserver.sh \
 && fix-permissions /opt/app-root -P

USER 1001
WORKDIR /opt/app-root/src

EXPOSE 8888

CMD ["/opt/app-root/bin/start-codeserver.sh"]
