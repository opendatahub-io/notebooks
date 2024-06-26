ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Access the client's secret for the subscription manager from the environment variable
ARG SECRET_DIR=/opt/app-root/src/.sec
ARG SERVERURL_DEFAULT=""
ARG BASEURL_DEFAULT=""

LABEL name="odh-notebook-rstudio-server-rhel9-python-3.9" \
      summary="RStudio Server image with python 3.9 based on Red Hat Enterprise Linux 9" \
      description="RStudio Server image with python 3.9 based on Red Hat Enterprise Linux 9" \
      io.k9s.display-name="RStudio Server image with python 3.9 based on Red Hat Enterprise Linux 9" \
      io.k9s.description="RStudio Server image with python 3.9 based on Red Hat Enterprise Linux 9" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/rstudio/rhel9-python-3.9" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:rstudio-rhel9-python-3.9"

USER root

# uncomment the bellow line if you fall on this error: subscription-manager is disabled when running inside a container. Please refer to your host system for subscription management.
#RUN sed -i 's/\(def in_container():\)/\1\n    return False/g' /usr/lib64/python*/*-packages/rhsm/config.py

# Run the subscription manager command using the provided credentials. Only include --serverurl and --baseurl if they are provided
RUN SERVERURL=$(cat ${SECRET_DIR}/SERVERURL 2>/dev/null || echo ${SERVERURL_DEFAULT}) && \
    BASEURL=$(cat ${SECRET_DIR}/BASEURL 2>/dev/null || echo ${BASEURL_DEFAULT}) && \
    USERNAME=$(cat ${SECRET_DIR}/USERNAME) && \
    PASSWORD=$(cat ${SECRET_DIR}/PASSWORD) && \
    subscription-manager register \
    ${SERVERURL:+--serverurl=$SERVERURL} \
    ${BASEURL:+--baseurl=$BASEURL} \
    --username=$USERNAME \
    --password=$PASSWORD \
    --force \
    --auto-attach

ENV R_VERSION=4.3.3

# Install R
RUN yum install -y yum-utils && \
    subscription-manager repos --enable codeready-builder-for-rhel-9-x86_64-rpms && \
    yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    INSTALL_PKGS="R-core R-core-devel R-java R-Rcpp R-highlight \
    R-littler R-littler-examples openssl-libs compat-openssl11" && \
    yum install -y --setopt=tsflags=nodocs $INSTALL_PKGS && \
    echo 'options(repos = c(CRAN = "https://cran.rstudio.com/"), download.file.method = "libcurl")' >> /usr/lib64/R/etc/Rprofile.site && \
    (umask 002;touch /usr/lib64/R/etc/Renviron.site) && \
    yum -y clean all --enablerepo='*'

# set R library to default (used in install.r from littler)
RUN chmod -R a+w /usr/lib64/R/library
ENV LIBLOC /usr/lib64/R/library

# set User R Library path
RUN mkdir -p /opt/app-root/bin/Rpackages/4.3 && chmod -R a+w /opt/app-root/bin/Rpackages/4.3
ENV R_LIBS_USER /opt/app-root/bin/Rpackages/4.3

WORKDIR /tmp/

# Install RStudio
RUN wget --progress=dot:giga https://download2.rstudio.org/server/rhel9/x86_64/rstudio-server-rhel-2023.12.1-402-x86_64.rpm && \
    yum install -y rstudio-server-rhel-2023.12.1-402-x86_64.rpm && \
    rm rstudio-server-rhel-2023.12.1-402-x86_64.rpm && \
    yum -y clean all  --enablerepo='*'

# Specific RStudio config and fixes
RUN chmod 1777 /var/run/rstudio-server && \
    mkdir -p /usr/share/doc/R
COPY rstudio/rhel9-python-3.9/rsession.conf /etc/rstudio/rsession.conf

# package installation 
RUN dnf install -y libsodium-devel.x86_64 libgit2-devel.x86_64 libcurl-devel harfbuzz-devel.x86_64 fribidi-devel.x86_64 cmake "flexiblas-*" && \
    dnf clean all && rm -rf /var/cache/yum
RUN R -e "install.packages('Rcpp')"

# Install NGINX to proxy RStudio and pass probes check
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
RUN yum -y module enable nginx:$NGINX_VERSION && \
    INSTALL_PKGS="nss_wrapper bind-utils gettext hostname nginx nginx-mod-stream nginx-mod-http-perl fcgiwrap initscripts chkconfig supervisor" && \
    yum install -y --setopt=tsflags=nodocs $INSTALL_PKGS && \
    rpm -V $INSTALL_PKGS && \
    nginx -v 2>&1 | grep -qe "nginx/$NGINX_VERSION\." && echo "Found VERSION $NGINX_VERSION" && \
    yum -y clean all --enablerepo='*'

COPY --chown=1001:0 rstudio/rhel9-python-3.9/supervisord/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy extra files to the image.
COPY rstudio/rhel9-python-3.9/nginx/root/ /

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

# Configure nginx
COPY rstudio/rhel9-python-3.9/nginx/serverconf/ /opt/app-root/etc/nginx.default.d/
COPY rstudio/rhel9-python-3.9/nginx/httpconf/ /opt/app-root/etc/nginx.d/
COPY rstudio/rhel9-python-3.9/nginx/api/ /opt/app-root/api/

# Launcher
WORKDIR /opt/app-root/bin

COPY rstudio/rhel9-python-3.9/utils utils/
COPY rstudio/rhel9-python-3.9/run-rstudio.sh rstudio/rhel9-python-3.9/setup_rstudio.py rstudio/rhel9-python-3.9/rsession.sh rstudio/rhel9-python-3.9/run-nginx.sh ./

# Unregister the system
RUN subscription-manager remove --all && subscription-manager unregister && subscription-manager clean

WORKDIR /opt/app-root/src

USER 1001

CMD ["/opt/app-root/bin/run-rstudio.sh"]
