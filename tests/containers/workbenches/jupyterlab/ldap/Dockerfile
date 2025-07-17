FROM quay.io/centos/centos:10

RUN dnf -y install \
        epel-release \
        dnf-plugins-core \
    && dnf config-manager --enable crb

# install OpenLDAP server + client tools + Cyrus SASL stack
RUN dnf -y install \
        openldap-servers \
        openldap-clients \
        openldap-devel \
        cyrus-sasl \
        cyrus-sasl-lib \
        cyrus-sasl-devel \
        cyrus-sasl-plain \
        cyrus-sasl-md5 \
        cyrus-sasl-gssapi \
        cyrus-sasl-ldap \
        cyrus-sasl-scram \
        && dnf clean all

# create runtime user & dirs
#RUN groupadd -r ldap -g 55 && \
#    useradd  -r -g ldap -u 55 -d /var/lib/ldap -s /sbin/nologin ldap

# default ports
EXPOSE 389 636

# volume mount points
#VOLUME ["/var/lib/ldap", "/etc/openldap/slapd.d"]

# simple entrypoint: start slapd in foreground
ENTRYPOINT ["/usr/sbin/slapd", "-u", "ldap", "-g", "ldap", "-d", "32768", "-h", "ldap:/// ldaps:///"]
