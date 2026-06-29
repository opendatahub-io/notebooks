#!/bin/bash

source /opt/app-root/etc/generate_container_user

set -e

source ${NGINX_CONTAINER_SCRIPTS_PATH}/common.sh

if [ ! -v NGINX_LOG_TO_VOLUME -a -v NGINX_LOG_PATH ]; then
    /bin/ln -sf /dev/stdout ${NGINX_LOG_PATH}/access.log
    /bin/ln -sf /dev/stderr ${NGINX_LOG_PATH}/error.log
fi

if [ -z "$NB_PREFIX" ]; then
    NB_PREFIX_FALLBACK="/"
else
    NB_PREFIX_FALLBACK="$NB_PREFIX"
fi

cat <<EOF > "${NGINX_CONFIGURATION_PATH}/http.conf"
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

map \$request \$loggable {
    ~\\/codeserver\\/healthz  0;
    default 1;
}

map \$time_iso8601 \$time_iso8601_p1 {
    ~([^+]+) \$1;
}
map \$time_iso8601 \$time_iso8601_p2 {
    ~\\+([0-9:]+)\$ \$1;
}
map \$msec \$millisec {
    ~\\.([0-9]+)\$ \$1;
}

log_format json escape=json '[{'
    '"id":"code-server",'
    '"name":"code-server",'
    '"last_activity":"\$time_iso8601_p1.\$millisec+\$time_iso8601_p2",'
    '"execution_state":"busy",'
    '"connections": 1'
    '}]';

map \$http_x_forwarded_proto \$custom_scheme {
    default \$scheme;
    https https;
}

map \$http_x_forwarded_prefix \$base_path {
    default \$http_x_forwarded_prefix;
    ""      ${NB_PREFIX_FALLBACK};
}

map \$base_path \$codeserver_base {
    "/"     "/codeserver/";
    default "\$base_path/codeserver/";
}

map \$base_path \$healthz_path {
    "/"     "/codeserver/healthz/";
    default "\$base_path/codeserver/healthz/";
}

map \$base_path \$api_kernels_path {
    "/"     "/api/kernels/";
    default "\$base_path/api/kernels/";
}

upstream workbench_server {
    server localhost:8787 max_fails=0;
}
EOF

if [ -z "$NB_PREFIX" ]; then
    export BASE_URL=""
    cp /opt/app-root/etc/nginx.default.d/proxy.conf.template /opt/app-root/etc/nginx.default.d/proxy.conf
else
    export BASE_URL=$(echo $NB_PREFIX | awk -F/ '{ print $4"-"$3 }')$(echo $NOTEBOOK_ARGS | grep -Po 'hub_host":"\K.*?(?=")' | awk -F/ '{ print $3 }' | awk -F. '{for (i=2; i<=NF; i++) printf ".%s", $i}')
    envsubst '${NB_PREFIX},${BASE_URL}' < /opt/app-root/etc/nginx.default.d/proxy.conf.template_nbprefix > /opt/app-root/etc/nginx.default.d/proxy.conf

    tmp=$(mktemp)
    envsubst '${BASE_URL}' < /etc/nginx/nginx.conf > "$tmp"
    cat "$tmp" > /etc/nginx/nginx.conf
    rm -f "$tmp"
fi

nginx
