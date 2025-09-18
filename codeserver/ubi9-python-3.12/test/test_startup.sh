set -Eeuxo pipefail

ROOT_DIR=$(dirname "$(readlink -f $0)")

projectName=projectName
notebookId=notebookId
translatedUsername=sometranslatedUsername
origin=https://origin

cat <<EOF > /tmp/notebook_args.env
--ServerApp.port=8888
--ServerApp.token=''
--ServerApp.password=''
--ServerApp.base_url=/notebook/${projectName}/${notebookId}
--ServerApp.quit_button=False
--ServerApp.tornado_settings={"user":"${translatedUsername}","hub_host":"${origin}","hub_prefix":"/projects/${projectName}"}
EOF

export NOTEBOOK_ARGS=$(cat /tmp/notebook_args.env)

export NB_PREFIX=/notebook/${projectName}/${notebookId}

/opt/app-root/bin/run-code-server.sh &
python3 ${ROOT_DIR}/probe_check.py ${projectName} ${notebookId} 8888
