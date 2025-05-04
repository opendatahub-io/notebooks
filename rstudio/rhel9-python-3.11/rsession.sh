#!/bin/bash

# Copy environment variables from PID 1, the container's root process
# This is to undo RStudio's purging of environment variables prior to launching rsession
# The idea of using `--rsession-path=rsession.sh` was suggested at
#  https://github.com/jupyterhub/jupyter-rsession-proxy/issues/135
# The command to clone (startup) environment variables from another process using Bash comes from
#  https://unix.stackexchange.com/questions/125110/how-do-i-source-another-processs-environment-variables
source <(xargs -0 bash -c 'printf "export %q\n" "$@"' -- < /proc/1/environ)

/usr/lib/rstudio-server/bin/rsession "$@"
