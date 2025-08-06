# Examples

## JupyterLab with Elyra

This Workbench image installs JupyterLab and the ODH-Elyra extension.

The main difference between the [upstream Elyra](https://github.com/elyra-ai/elyra) and the [ODH-Elyra fork](https://github.com/opendatahub-io/elyra) is that the fork implements Argo Pipelines support, which is required for executing pipelines in OpenDataHub/OpenShift AI.
Specifically, the fork already includes the changes from [elyra-ai/elyra #3273](https://github.com/elyra-ai/elyra/pull/3273), which is still pending upstream.

### Design

The workbench is based on a Source-to-Image (S2I) UBI9 Python 3.11 image.
This means—besides having Python 3.11 installed—that it also has the following
* Python virtual environment at `/opt/app-root` is activated by default
* `HOME` directory is set to `/opt/app-root/src`
* port 8888 is `EXPOSE`D by default

These characteristics are required for OpenDataHub workbenches to function.

#### Integration with OpenDataHub Notebook Controller and Notebook Dashboard

#### OpenDataHub Dashboard

Dashboard automatically populates an environment variable named `NOTEBOOK_ARGS` when starting a container from this image.
This variable contains configurations that are necessary to integrate with Dashboard regarding launching the Workbench and logging off.

Reference: https://github.com/opendatahub-io/odh-dashboard/blob/95d80a0cccd5053dc0ca372effcdcd8183a0d5b8/frontend/src/api/k8s/notebooks.ts#L143-L149

Furthermore, when configuring a workbench, the default Persistent Volume Claim (PVC) is created and volume is mounted at `/opt/app-root/src` in the workbench container.
This means that changing the user's `HOME` directory from the expected default is inadvisable.
It further means that whatever the original content of `/opt/app-root/src` in the image may be, it will be shadowed by the PVC.

##### OpenDataHub Notebook Controller

During the Notebook Custom Resource (CR) creation, the mutating webhook in Notebook Controller is triggered.
This webhook is responsible for configuring OAuth Proxy, certificate bundles, pipeline runtime, runtime images, and maybe more.
It also creates a service and OpenShift route to make the Workbench reachable from the outside of the cluster.

**OAuth Proxy** is configured to connect to port 8888 of the workbench container (discussed above) and listen for incoming connections on port 8443.

Reference: https://github.com/opendatahub-io/kubeflow/blob/eacf63cdaed4db766a6503aa413e388e1d2721ef/components/odh-notebook-controller/controllers/notebook_webhook.go#L114-L121

**Certificate bundles** are added as a file-mounted configmap at `/etc/pki/tls/custom-certs/ca-bundle.crt`.
This is a nonstandard location, so it is necessary to also add environment variables that instruct various software to reference this bundle during operation.

Reference:
* https://github.com/opendatahub-io/kubeflow/blob/eacf63cdaed4db766a6503aa413e388e1d2721ef/components/odh-notebook-controller/controllers/notebook_webhook.go#L598
* https://github.com/opendatahub-io/kubeflow/blob/eacf63cdaed4db766a6503aa413e388e1d2721ef/components/odh-notebook-controller/controllers/notebook_webhook.go#L601-L607

**Pipeline runtime configuration** is obtained from a Data Science Pipeline Application (DSPA) CR.
The DSPA CR is first located in the same project where the workbench is being started, a secret with the connection data is created, and then this secret is mounted.
The secret is mounted under `/opt/app-root/runtimes/`.

Reference: https://github.com/opendatahub-io/kubeflow/blob/eacf63cdaed4db766a6503aa413e388e1d2721ef/components/odh-notebook-controller/controllers/notebook_dspa_secret.go#L42C28-L42C50

IMPORTANT: the `setup-elyra.sh` script in this repo relies on this location.

**Runtime images** are processed very similarly to the DSPA configuration.
First, image stream resources are examined, and then a configmap is created and mounted to every newly started workbench.
The mount location is under `/opt/app-root/pipeline-runtimes/`.

Reference: https://github.com/opendatahub-io/kubeflow/blob/eacf63cdaed4db766a6503aa413e388e1d2721ef/components/odh-notebook-controller/controllers/notebook_runtime.go#L25C19-L25C51

IMPORTANT: the `setup-elyra.sh` script in this repo again relies on this location.

### Build

```shell
podman build -f examples/jupyterlab-with-elyra/Dockerfile -t quay.io/your-username/jupyterlab-with-elyra:latest .
podman push quay.io/your-username/jupyterlab-with-elyra:latest
```

### Deploy

Open the `Settings > Workbench images` page in OpenDataHub Dashboard.
Click on the `Import new image` button and add the image you have just pushed.
The `Image location` field should be set to `quay.io/your-username/jupyterlab-with-elyra:latest`, or wherever the image is pushed and available for the cluster to pull.
Values of other fields do not matter for functionality, but they let you keep better track of previously imported images.

There is a special ODH Dashboard feature that alerts you when you are using a workbench image that lists the `elyra` instead of `odh-elyra` package.
This code will have to be updated when `elyra` also gains support for Argo Pipelines, but for now it does the job.

Reference: https://github.com/opendatahub-io/odh-dashboard/blob/2ced77737a1b1fc24b94acac41245da8b29468a4/frontend/src/concepts/pipelines/elyra/utils.ts#L152-L162
