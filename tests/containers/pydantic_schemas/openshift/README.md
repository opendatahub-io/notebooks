Openshift schemas as [Pydantic](https://pydantic-docs.helpmanual.io/) datamodels

Generated with [koxudaxi/datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator)
from [Kubernetes's OpenAPI Specification](https://github.com/kubernetes/kubernetes/tree/master/api/openapi-spec)

Openshift does not seem to be publishing their API anymore
([openshift/origin#25643](https://github.com/openshift/origin/issues/25643)), so fetch from live cluster.

```shell
$ oc get --raw /openapi/v2 > openapi-v2.json
```

Expect the generation to take long time (minutes)

```shell
datamodel-codegen --input-file-type json --input openapi-v2.json --output model.py
```

See also [airspot-dev/k8s-datamodels](https://github.com/airspot-dev/k8s-datamodels) that generates
from [Kubernetes's OpenAPI Specification](https://github.com/kubernetes/kubernetes/tree/master/api/openapi-spec)
