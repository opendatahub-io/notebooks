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

# Install Python kernel support for VS Code
RUN pip install --no-cache-dir jupyter ipykernel

# Ensure writable dirs for code-server data
RUN mkdir -p ${APP_ROOT}/src/.local/share/code-server \
 && fix-permissions ${APP_ROOT} -P

USER 1001
WORKDIR ${APP_ROOT}/src

EXPOSE 8080

CMD ["code-server", \
     "--bind-addr", "0.0.0.0:8080", \
     "--auth", "none", \
     "--disable-telemetry", \
     "--disable-update-check", \
     "--disable-getting-started-override", \
     "/opt/app-root/src"]
