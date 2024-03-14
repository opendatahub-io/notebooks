# This image provides an Anaconda-based Python 3.8 environment you can use to run your
# Python applications.
FROM registry.access.redhat.com/ubi8/s2i-base AS s2i-python-anaconda-38-base

EXPOSE 8080

# TODO(Spryor): ensure these are right, add Anaconda versions
ENV PYTHON_VERSION=3.8 \
    PATH=$HOME/.local/bin/:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off

ENV SUMMARY="Platform for building and running Anaconda Python $PYTHON_VERSION applications" \
    DESCRIPTION="Anaconda Python $PYTHON_VERSION available as container is a base \
    platform for building and running various Anaconda Python $PYTHON_VERSION \
    applications and frameworks. Python is an easy to learn, powerful programming \
    language. It has efficient high-level data structures and a simple but effective \
    approach to object-oriented programming. Python's elegant syntax and dynamic \
    typing, together with its interpreted nature, make it an ideal language for \
    scripting and rapid application development in many areas on most platforms."

LABEL summary="$SUMMARY" \
      description="$DESCRIPTION" \
      io.k8s.description="$DESCRIPTION" \
      io.k8s.display-name="Anaconda Python 3.8" \
      io.openshift.expose-services="8080:http" \
      io.openshift.tags="anaconda,builder,python,python38,python-38,anaconda-python38" \
      name="anaconda-python38" \
      version="1" \
      usage="s2i build https://github.com/sclorg/s2i-python-container.git --context-dir=3.8/test/setup-test-app/ ubi8/python-38 python-sample-app" \
      maintainer="spryor@redhat.com for now..."


ARG ANACONDA_INSTALLER_NAME=Miniconda3-latest-Linux-x86_64.sh

RUN INSTALL_PKGS="nss_wrapper \
    httpd httpd-devel mod_ssl mod_auth_gssapi mod_ldap \
    mod_session atlas-devel gcc-gfortran libffi-devel libtool-ltdl enchant" && \
    curl -O https://repo.anaconda.com/miniconda/${ANACONDA_INSTALLER_NAME} && \
    chmod +x ${ANACONDA_INSTALLER_NAME} && \
    ./${ANACONDA_INSTALLER_NAME} -b -p /opt/anaconda3 && \
    rm ./${ANACONDA_INSTALLER_NAME} && \
    /opt/anaconda3/bin/conda init && \
    yum -y module disable python38:3.8 && \
    yum -y module enable httpd:2.4 && \
    yum -y --setopt=tsflags=nodocs update && \
    yum -y --setopt=tsflags=nodocs install $INSTALL_PKGS && \
    rpm -V $INSTALL_PKGS && \
    # Remove redhat-logos-httpd (httpd dependency) to keep image size smaller.
    rpm -e --nodeps redhat-logos-httpd && \
    yum -y clean all --enablerepo='*'

# Copy the S2I scripts to $STI_SCRIPTS_PATH.
COPY ./s2i/bin/ $STI_SCRIPTS_PATH

COPY environment.yml ./
# - Create a Python virtual environment for use by any application to avoid
#   potential conflicts with Python packages preinstalled in the main Python
#   installation.
# - In order to drop the root user, we have to make some directories world
#   writable as OpenShift default security model is to run the container
#   under random UID.
RUN /opt/anaconda3/bin/conda env create --file environment.yml -p "${APP_ROOT}" && \
    rm environment.yml && \
    chown -R 1001:0 ${APP_ROOT} && \
    fix-permissions ${APP_ROOT} -P && \
    fix-permissions /opt/anaconda3 -P && \
    rpm-file-permissions

# For RHEL/Centos 8+ scl_enable isn't sourced automatically in s2i-core
# so virtualenv needs to be activated this way
ENV BASH_ENV="source /opt/anaconda3/bin/activate ${APP_ROOT}" \
    ENV="source /opt/anaconda3/bin/activate ${APP_ROOT}" \
    PROMPT_COMMAND=". /opt/anaconda3/bin/activate ${APP_ROOT}"

USER 1001

# Set the default CMD to print the usage of the language image.
CMD $STI_SCRIPTS_PATH/usage


FROM s2i-python-anaconda-38-base

LABEL name="odh-notebook-base-ubi8-anaconda-python-3.8" \
      summary="Anaconda based Python 3.8 base image for ODH notebooks" \
      description="Anaconda Base Python 3.8 builder image based on UBI8 for ODH notebooks" \
      io.k8s.display-name="Anaconda Python 3.8 base image for ODH notebooks" \
      io.k8s.description="Anaconda Base Python 3.8 builder image based on UBI8 for ODH notebooks"

WORKDIR /opt/app-root/bin

# Install the oc client
RUN curl -L https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz \
        -o /tmp/openshift-client-linux.tar.gz && \
    tar -xzvf /tmp/openshift-client-linux.tar.gz oc && \
    rm -f /tmp/openshift-client-linux.tar.gz

# Fix permissions to support pip in Openshift environments
RUN fix-permissions /opt/app-root -P

WORKDIR /opt/app-root/src
