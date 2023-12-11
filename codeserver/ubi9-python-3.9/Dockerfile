ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG CODESERVER_VERSION=v4.16.1

LABEL name="odh-notebook-code-server-ubi9-python-3.9" \
      summary="Code Server (VS Code) image with python 3.9 based on UBI 9" \
      description="Code Server (VS Code) image with python 3.9 based on UBI9" \
      io.k8s.display-name="Code Server (VS Code) image with python 3.9 based on UBI9" \
      io.k8s.description="Code Server (VS Code) image with python 3.9 based on UBI9" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/codeserver/ubi9-python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:codeserver-ubi9-python-3.9"

USER 0

WORKDIR /opt/app-root/bin

# Install usefull packages from Pipfile.lock
COPY Pipfile.lock ./

# Install packages and cleanup
RUN echo "Installing softwares and packages" && \
    micropipenv install && \
    rm -f ./Pipfile.lock && \
    # Fix permissions to support pip in Openshift environments \
    chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

# Install usefull OS packages
RUN dnf install -y jq git-lfs libsndfile

# Install Code Server
RUN yum install -y "https://github.com/coder/code-server/releases/download/${CODESERVER_VERSION}/code-server-${CODESERVER_VERSION/v/}-amd64.rpm" && \
    yum -y clean all --enablerepo='*'

# Change ownership of relevant directories
RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
    fix-permissions /opt/app-root -P

# Install NGINX to proxy VSCode and pass probes check
ENV NGINX_VERSION=1.22 \
    NGINX_SHORT_VER=122 \
    NGINX_CONFIGURATION_PATH=${APP_ROOT}/etc/nginx.d \
    NGINX_CONF_PATH=/etc/nginx/nginx.conf \
    NGINX_DEFAULT_CONF_PATH=${APP_ROOT}/etc/nginx.default.d \
    NGINX_CONTAINER_SCRIPTS_PATH=/usr/share/container-scripts/nginx \
    NGINX_APP_ROOT=${APP_ROOT} \
    NGINX_LOG_PATH=/var/log/nginx \
    NGINX_PERL_MODULE_PATH=${APP_ROOT}/etc/perl

# Modules does not exist
RUN yum install -y https://download.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    INSTALL_PKGS="bind-utils nginx nginx-mod-stream nginx-mod-http-perl fcgiwrap initscripts chkconfig" && \
    yum install -y --setopt=tsflags=nodocs $INSTALL_PKGS && \
    rpm -V $INSTALL_PKGS && \
    # spawn-fcgi is not in epel9 \
    rpm -i --nodocs https://www.rpmfind.net/linux/fedora/linux/releases/37/Everything/x86_64/os/Packages/s/spawn-fcgi-1.6.3-23.fc37.x86_64.rpm && \
    yum -y clean all --enablerepo='*'

# Copy extra files to the image.
COPY nginx/root/ /

# Changing ownership and user rights to support following use-cases:
# 1) running container on OpenShift, whose default security model
#    is to run the container under random UID, but GID=0
# 2) for working root-less container with UID=1001, which does not have
#    to have GID=0
# 3) for default use-case, that is running container directly on operating system,
#    with default UID and GID (1001:0)
# Supported combinations of UID:GID are thus following:
# UID=1001 && GID=0
# UID=<any>&& GID=0
# UID=1001 && GID=<any>
RUN sed -i -f ${NGINX_APP_ROOT}/nginxconf.sed ${NGINX_CONF_PATH} && \
    mkdir -p ${NGINX_APP_ROOT}/etc/nginx.d/ && \
    mkdir -p ${NGINX_APP_ROOT}/etc/nginx.default.d/ && \
    mkdir -p ${NGINX_APP_ROOT}/api/ && \
    mkdir -p ${NGINX_CONTAINER_SCRIPTS_PATH}/nginx-start && \
    mkdir -p ${NGINX_LOG_PATH} && \
    mkdir -p ${NGINX_PERL_MODULE_PATH} && \
    chown -R 1001:0 ${NGINX_CONF_PATH} && \
    chown -R 1001:0 ${NGINX_APP_ROOT}/etc && \
    chown -R 1001:0 ${NGINX_CONTAINER_SCRIPTS_PATH}/nginx-start && \
    chown -R 1001:0 /var/lib/nginx /var/log/nginx /run && \
    chmod    ug+rw  ${NGINX_CONF_PATH} && \
    chmod -R ug+rwX ${NGINX_APP_ROOT}/etc && \
    chmod -R ug+rwX ${NGINX_CONTAINER_SCRIPTS_PATH}/nginx-start && \
    chmod -R ug+rwX /var/lib/nginx /var/log/nginx /run && \
    rpm-file-permissions

## Configure nginx
COPY nginx/serverconf/ /opt/app-root/etc/nginx.default.d/
COPY nginx/httpconf/ /opt/app-root/etc/nginx.d/
COPY nginx/api/ /opt/app-root/api/

# Launcher
COPY --chown=1001:0 utils utils/
COPY --chown=1001:0 run-code-server.sh run-nginx.sh ./

ENV SHELL /bin/bash

WORKDIR /opt/app-root/src

USER 1001

CMD /opt/app-root/bin/run-code-server.sh
