# The server-side authentication_ldap_sasl plugin is only shipped with MySQL Enterprise Edition.
# Therefore let's use Percona Server instead https://docs.percona.com/percona-server/8.0/ldap-authentication.html
FROM docker.io/percona/percona-server:8.4

USER 0
RUN microdnf install -y \
    cyrus-sasl \
    cyrus-sasl-plain \
    shadow-utils \
    && microdnf clean all

# Copy our custom configuration files into the image
#COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY mysql.conf /etc/sasl2/mysql.conf
COPY etc_pam.d_mysqld /etc/pam.d/mysqld
COPY run.sh /run.sh

# Make the run script executable
RUN chmod +x /run.sh

# Expose the MySQL port
EXPOSE 3306

# The command to run when the container starts
ENTRYPOINT ["/run.sh"]
