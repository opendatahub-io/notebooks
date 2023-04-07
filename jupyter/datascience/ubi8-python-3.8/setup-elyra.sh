#!/bin/bash
set -x

replace_invalid_characters (){
  python -c 'import sys;print(sys.argv[1].translate ({ord(c): "-" for c in "!@#$%^&*()[]{};:,/<>?\|`~=_+"}))' "$1"
}

# Set the elyra config on the right path
cp /opt/app-root/bin/utils/jupyter_elyra_config.py /opt/app-root/src/.jupyter/

# Assumptions are existing kubeflow installation is in the kubeflow namespace
DEFAULT_RUNTIME_FILE=$(jupyter --data-dir)/metadata/runtimes/my_kfp.json

if [ -f "/var/run/secrets/kubernetes.io/serviceaccount/namespace" ]; then
  SA_NAMESPACE=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)
fi

COS_BUCKET=$(replace_invalid_characters "$COS_BUCKET")
export COS_BUCKET=${COS_BUCKET:-default}

# If Kubeflow credentials are not supplied, use default Kubeflow installation credentials
KF_DEPLOYMENT_NAMESPACE="${SA_NAMESPACE:=default}"
AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:=minio}"
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:=minio123}"

if [[ ! -f "$DEFAULT_RUNTIME_FILE" ]]; then
  elyra-metadata install runtimes --schema_name=kfp \
                                  --name=my_kfp \
                                  --display_name=Default \
                                  --auth_type=NO_AUTHENTICATION \
                                  --api_endpoint=http://ml-pipeline."$KF_DEPLOYMENT_NAMESPACE".svc.cluster.local:3000/pipeline \
                                  --cos_endpoint=http://minio-service."$KF_DEPLOYMENT_NAMESPACE".svc.cluster.local:9000 \
                                  --cos_auth_type=USER_CREDENTIALS \
                                  --cos_username="$AWS_ACCESS_KEY_ID" \
                                  --cos_password="$AWS_SECRET_ACCESS_KEY" \
                                  --cos_bucket="$COS_BUCKET" \
                                  --engine=Tekton
fi
