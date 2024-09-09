# Habana Notebook Image
This directory contains the Dockerfile to build a Notebook image compatible with 1.17.1 Habana Version.

Currently supporting the support matrix: https://docs.habana.ai/en/v1.17.1/Support_Matrix/Support_Matrix.html

| Firmware                  | version          |
| ------------------------- | ---------------- |
| First-gen Gaudi Firmware  | 1.2.3            |
| Gaudi 2 Firmware          | 1.17.0-fw-51.2.0 |
| Gaudi 3 Firmware          | 1.17.1-fw-51.5.0 |

| Python-package | version |
| -------------- | ------- |
| torch          | 2.4.0   |
| pandas         | 2.2.2   |
| numpy          | 2.1.0   |
| scipy          | 1.14.1  |

### Build and execution commands

To build the Habana 1.17.1, you can point to your own Quay.io registry, as follows:

> Remember, the `PUSH_IMAGES=no` flag will skip uploading images to Quay.io and the `CONTAINER_BUILD_CACHE_ARGS=""` flag will force to use local cache for development purposes

```bash
$ export QUAY_IO=quay.io/{myuser}/workbench-images
$ export WORKBENCH_RELEASE=2024a
$ make habana-jupyter-1.17.1-ubi9-python-3.11 \
    -e IMAGE_REGISTRY=$QUAY_IO \
    -e RELEASE=$WORKBENCH_RELEASE \
    -e PUSH_IMAGES=no \
    -e CONTAINER_BUILD_CACHE_ARGS=""
```

To run the container, you can get the latest tag in Podman and run it automatically:

```bash
$ export LATEST_TAG=`podman images --format "{{.Repository}}:{{.Tag}}" | grep "$QUAY_IO:habana-jupyter-1.17.1-ubi9-python-3.11-$WORKBENCH_RELEASE" | sort -r | head -n1 | cut -d':' -f2`
$ podman run -it -p 8888:8888 $QUAY_IO:$LATEST_TAG
```

### References

Repository branch:

- https://github.com/HabanaAI/Setup_and_Install/tree/1.17.1

For further documentation related to HabanaAI, please refer:

- https://docs.habana.ai/en/v1.17.1/Gaudi_Overview/index.html
