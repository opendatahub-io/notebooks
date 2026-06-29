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
    nb_prefix_part=$(echo "$NB_PREFIX" | awk -F/ '{
        n = 0
        for (i = 1; i <= NF; i++) if ($i != "") seg[++n] = $i
        if (n >= 2) print seg[n] "-" seg[n - 1]
    }')
    if [ -z "$nb_prefix_part" ] || [[ "$nb_prefix_part" != *-* ]] \
        || [ -z "${nb_prefix_part%%-*}" ] || [ -z "${nb_prefix_part#*-}" ]; then
        nb_prefix_part=""
    fi
    hub_host_suffix=$(echo "$NOTEBOOK_ARGS" | grep -Po 'hub_host":"\K.*?(?=")' | awk -F/ '{ print $3 }' | awk -F. '{for (i=2; i<=NF; i++) printf ".%s", $i}')
    BASE_URL="${nb_prefix_part}${hub_host_suffix}"

    if [ -z "$BASE_URL" ] || [ "$BASE_URL" = "$nb_prefix_part" ]; then
        export BASE_URL=""
    else
        export BASE_URL
    fi
    envsubst '${NB_PREFIX},${BASE_URL}' < /opt/app-root/etc/nginx.default.d/proxy.conf.template_nbprefix > /opt/app-root/etc/nginx.default.d/proxy.conf

    # A temp file is used because piping envsubst directly into the same file via `tee`
    # is a race condition: `tee` can truncate the file before `envsubst` finishes reading it,
    # resulting in an empty/corrupt config and "no events section" errors from nginx.
    tmp=$(mktemp)
    envsubst '${BASE_URL}' < /etc/nginx/nginx.conf > "$tmp"
    cat "$tmp" > /etc/nginx/nginx.conf
    rm -f "$tmp"
fi

nginx