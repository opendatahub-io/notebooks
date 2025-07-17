#!/bin/bash
set -Eeuxo pipefail

# Create a non-root user for the test
# and set a password for it.
useradd testuser
echo "testuser:testpassword" | chpasswd

groupadd -r sasl
# Create the run directory for saslauthd
mkdir -p /var/run/saslauthd
chown root:sasl /var/run/saslauthd

runuser -u mysql -- mysqld --initialize-insecure
#mkdir -p /var/lib/mysql
#chown mysql:mysql /var/lib/mysql
#chmod 750 /var/lib/mysql

# Add the mysql user to the sasl group so it can communicate with saslauthd
usermod -a -G sasl mysql

#echo "Starting supervisor..."
#exec /usr/bin/supervisord

echo 'START=yes'          > /etc/sysconfig/saslauthd
echo 'MECH=pam'          >> /etc/sysconfig/saslauthd
echo "OPTIONS='-c -m /var/run/saslauthd'" >> /etc/sysconfig/saslauthd

export SASL_LOG_LEVEL=7

#/usr/sbin/saslauthd -d -a pam &
/usr/sbin/saslauthd -d -a pam -m /var/run/saslauthd &
# Give saslauthd a moment to start up
sleep 1

#SET PERSIST authentication_ldap_sasl_server_host='slapd';
#SET PERSIST authentication_ldap_sasl_bind_base_dn='dc=example,dc=com';

runuser -u mysql -- mysqld --bind-address=0.0.0.0 --plugin-load-add=authentication_ldap_sasl.so --authentication-ldap-sasl-auth-method-name=PLAIN --authentication-ldap-sasl-server-host=slapd --authentication_ldap_sasl_bind_base_dn='dc=example,dc=com' &
# Wait for the MySQL server to start
#bash -c 'timeout 30 bash -c "until [ -S /var/run/mysqld/mysqld.sock ]; do sleep 0.5; done"'
bash -c 'timeout 30 bash -c "until [ -S /var/lib/mysql/mysql.sock ]; do sleep 0.5; done"'

#INSTALL PLUGIN authentication_ldap_sasl
#  SONAME 'authentication_ldap_sasl.so';

mysql -uroot \
  -e "SELECT PLUGIN_NAME, PLUGIN_STATUS
      FROM INFORMATION_SCHEMA.PLUGINS
      WHERE PLUGIN_NAME='authentication_ldap_sasl';"

# CREATE USER 'testuser'@'%'
#  IDENTIFIED WITH authentication_ldap_sasl;

# CREATE USER 'testuser'@'%'
#  IDENTIFIED WITH authentication_ldap_sasl
#  BY 'uid=testuser,ou=People,dc=example,dc=com';

# https://dba.stackexchange.com/questions/124964/error-2013-hy000-lost-connection-to-mysql-server-during-query-while-load-of-my

mysql -u root <<EOF
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'StrongRootPass!';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;

CREATE USER 'testuser'@'%'
  IDENTIFIED WITH authentication_ldap_sasl
  BY 'uid=testuser,ou=People,dc=example,dc=com';

FLUSH PRIVILEGES;

SET GLOBAL connect_timeout = 10;

EOF

sleep 1

#mysql -u testuser -p testpassword -e "SELECT VERSION();"

#exec /usr/local/bin/docker-entrypoint.sh mysqld

wait
