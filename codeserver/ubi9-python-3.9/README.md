# codeserver-ubi9-python-3.11

To run the following image, you can use the following command:

```bash
$ export QUAY_IO=quay.io/{myuser}/workbench-images
$ export WORKBENCH_RELEASE=2024b
$ make codeserver-ubi9-python-3.9 \
    -e IMAGE_REGISTRY=$QUAY_IO \
    -e RELEASE=$WORKBENCH_RELEASE \
    -e PUSH_IMAGES=no \
    -e CONTAINER_BUILD_CACHE_ARGS=""
```

To execute with Podman, do as follows:

```bash
$ export LATEST_TAG=`podman images --format "{{.Repository}}:{{.Tag}}" | grep "$QUAY_IO:codeserver-ubi9-python-3.9-$WORKBENCH_RELEASE" | sort -r | head -n1 | cut -d':' -f2`
$ podman run -it -p 8787:8787 $QUAY_IO:$LATEST_TAG
```
