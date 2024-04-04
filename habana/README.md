# Habana Notebook Image
This directory contains the Dockerfiles to build Notebook images compatible with HabanaAI Gaudi Devices.  

Currently supporting the support matrix:  
https://docs.habana.ai/en/latest/Support_Matrix/Support_Matrix_v1.9.0.html   
https://docs.habana.ai/en/latest/Support_Matrix/Support_Matrix_v1.10.0.html   
https://docs.habana.ai/en/latest/Support_Matrix/Support_Matrix_v1.13.0.html   
https://docs.habana.ai/en/latest/Support_Matrix/Support_Matrix.html  


### Setup Habana AI on Openshift.  

The device on AWS with machine `dl1.24xlarge` has habana firmware.  
With documentation for [OpenShift Enviornment](https://docs.habana.ai/en/latest/Orchestration/HabanaAI_Operator/index.html?highlight=openshift).  


### Utilize with OpenDatahub

User can use the Habana base notebook image with OpenDatahub, 
With the [notebook manifests](../manifests/base/jupyter-habana-notebook-imagestream.yaml),  
user can include the habanaAI compatible image directly to Opendatahub.

### Reference  

https://github.com/HabanaAI/Setup_and_Install/tree/1.9.0  
https://github.com/HabanaAI/Setup_and_Install/tree/1.10.0  
https://github.com/HabanaAI/Setup_and_Install/tree/1.11.0  
https://github.com/HabanaAI/Setup_and_Install/tree/1.13.0  


For further documentation related to HabanaAI, please refer:  
https://docs.habana.ai/en/v1.9.0/Gaudi_Overview/index.html   
https://docs.habana.ai/en/v1.10.0/Gaudi_Overview/index.html  
https://docs.habana.ai/en/v1.11.0/Gaudi_Overview/index.html  
https://docs.habana.ai/en/v1.13.0/Gaudi_Overview/index.html
