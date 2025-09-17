set -Eeuxo pipefail

ROOT_DIR=$(dirname "$(readlink -f $0)")

projectName=projectName
notebookId=notebookId
translatedUsername=sometranslatedUsername
origin=https://origin

# (outdated?) https://github.com/opendatahub-io/odh-dashboard/blob/2.4.0-release/backend/src/utils/notebookUtils.ts#L284-L293
# https://github.com/opendatahub-io/odh-dashboard/blob/1d5a9065c10acc4706b84b06c67f27f16cf6dee7/frontend/src/api/k8s/notebooks.ts#L157-L170
cat <<EOF > /tmp/notebook_args.env
--ServerApp.port=8888
--ServerApp.token=''
--ServerApp.password=''
--ServerApp.base_url=/notebook/${projectName}/${notebookId}
--ServerApp.quit_button=False
--ServerApp.tornado_settings={"user":"${translatedUsername}","hub_host":"${origin}","hub_prefix":"/projects/${projectName}"}
EOF

export NOTEBOOK_ARGS=$(cat /tmp/notebook_args.env)

# NB_PREFIX is set by notebook-controller and codeserver scripting depends on it
# https://github.com/opendatahub-io/kubeflow/blob/f924a96375988fe3801db883e99ce9ed1ab5939c/components/notebook-controller/controllers/notebook_controller.go#L417
export NB_PREFIX=/notebook/${projectName}/${notebookId}

/opt/app-root/bin/run-code-server.sh &
python3 ${ROOT_DIR}/probe_check.py ${projectName} ${notebookId} 8888
