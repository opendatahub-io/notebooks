# Change port; run-nginx.sh removes the IPv6 listen at runtime when IPv6 is disabled via sysctl.
/listen/s%80%8888 default_server%

# Keep Location headers relative so port-mapped container tests and routes preserve the client port.
/server {/a\        absolute_redirect off;

# One worker only
/worker_processes/s%auto%1%

s/^user *nginx;//
s%/etc/nginx/conf.d/%/opt/app-root/etc/nginx.d/%
s%/etc/nginx/default.d/%/opt/app-root/etc/nginx.default.d/%
s%/usr/share/nginx/html%/opt/app-root/src%

# See: https://github.com/sclorg/nginx-container/pull/69
/error_page/d
/40x.html/,+1d
/50x.html/,+1d

# Route nginx server_name through NB_PREFIX when set by the platform
/server_name/s%server_name  _%server_name  ${BASE_URL}%
