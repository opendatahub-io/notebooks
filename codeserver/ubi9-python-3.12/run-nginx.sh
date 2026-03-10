#!/bin/bash

source /opt/app-root/etc/generate_container_user

set -e

source ${NGINX_CONTAINER_SCRIPTS_PATH}/common.sh

# disabled, only used to source nginx files in user directory
#process_extending_files ${NGINX_APP_ROOT}/src/nginx-start ${NGINX_CONTAINER_SCRIPTS_PATH}/nginx-start

if [ ! -v NGINX_LOG_TO_VOLUME -a -v NGINX_LOG_PATH ]; then
    /bin/ln -sf /dev/stdout ${NGINX_LOG_PATH}/access.log
    /bin/ln -sf /dev/stderr ${NGINX_LOG_PATH}/error.log
fi

# substitute NB_PREFIX in proxy configuration if it exists
if [ -z "$NB_PREFIX" ]; then
    cp /opt/app-root/etc/nginx.default.d/proxy.conf.template /opt/app-root/etc/nginx.default.d/proxy.conf
else
    export BASE_URL=$(echo "$NB_PREFIX" | awk -F/ '{ print $4"-"$3 }')$(echo "$NOTEBOOK_ARGS" | grep -Po 'hub_host":"\K.*?(?=")' | awk -F/ '{ print $3 }' | awk -F. '{for (i=2; i<=NF; i++) printf ".%s", $i}')
    # If BASE_URL is empty or invalid (missing hub_host), use wildcard server_name
    if [ -z "$BASE_URL" ] || [ "$BASE_URL" = "$(echo "$NB_PREFIX" | awk -F/ '{ print $4"-"$3 }')" ]; then
        export BASE_URL="_"
    fi
    # Substitute ${NB_PREFIX} and ${BASE_URL} placeholders in the proxy config template.
    envsubst '${NB_PREFIX},${BASE_URL}' < /opt/app-root/etc/nginx.default.d/proxy.conf.template_nbprefix > /opt/app-root/etc/nginx.default.d/proxy.conf

    # Substitute ${BASE_URL} in the main nginx.conf (placed there at build time by nginxconf.sed).
    # A temp file is used because piping envsubst directly into the same file via `tee`
    # is a race condition: `tee` can truncate the file before `envsubst` finishes reading it,
    # resulting in an empty/corrupt config and "no events section" errors from nginx.
    tmp=$(mktemp)
    envsubst '${BASE_URL}' < /etc/nginx/nginx.conf > "$tmp"
    cat "$tmp" > /etc/nginx/nginx.conf
    rm -f "$tmp"
fi

nginx