
Workbench images are supported for a minimum of one year. Major updates to pre-configured notebook images occur approximately every six months. Therefore, two supported notebook images are typically available at any given time. If necessary, you can still access older notebook images from the registry, even if they are no longer supported. You can then add the older notebook images as custom notebook images to cater to the project’s specific requirements.

Open Data Hub contains the following workbench images with different variations:

| Workbenches                | ODH     | OpenShift AI | OS     | GPU     | Runtimes |
| -------------------------- | ------- | ------------ | ------ | ------- | -------- |
| Jupyter Minimal            | &#9745; | &#9745;      | UBI8/9 | &#9746; | &#9746;  |
| CUDA                       | &#9745; | &#9745;      | UBI8/9 | &#9745; | &#9746;  |
| HabanaAI                   | &#9745; | &#9746;      | UBI8/9 | &#9745; | &#9746;  |
| Jupyter Data Science       | &#9745; | &#9745;      | UBI8/9 | &#9746; | &#9745;  |
| Jupyter Tensorflow         | &#9745; | &#9745;      | UBI8/9 | &#9745; | &#9745;  |
| Jupyter PyTorch            | &#9745; | &#9745;      | UBI8/9 | &#9745; | &#9745;  |
| Jupyter TrustyAI           | &#9745; | &#9745;      | UBI9   | &#9746; | &#9746;  |
| code-server                | &#9745; | &#9746;      | C9S    | &#9746; | &#9746;  |
| RStudio Server            | &#9745; | &#9746;      | C9S    | &#9745; | &#9746;  |

These notebooks are incorporated to be used in conjunction with Open Data Hub, specifically utilizing the ODH Notebook Controller as the launching platform. The table above provides insights into the characteristics of each notebook, including their availability in both ODH and OpenShift AI environments, GPU support, and whether they are offered as runtimes ie without the JupyterLab UI.  

All the notebooks are available on the[ Quay.io registry](https://quay.io/repository/opendatahub/workbench-images?tab=tags&tag=latest); please filter the results by using the tag "2023b" for the latest release and "2023a" for the n-1.

## Jupyter Minimal
Jupyter Minimal provides a browser-based integrated development environment where you can write, edit, and debug code using the familiar interface and features of JupyterLab. 
If you do not require advanced machine learning features or additional resources for compute-intensive data science work, you can use the Minimal Python image to develop your models.

[2023b Packages](https://github.com/opendatahub-io/notebooks/blob/2023b/jupyter/minimal/ubi9-python-3.9/Pipfile) || [2023a Packages](https://github.com/opendatahub-io/notebooks/blob/2023a/jupyter/minimal/ubi9-python-3.9/Pipfile)


## CUDA

CUDA provides a browser-based integrated development environment where you can write, edit, and debug code using the familiar interface and features of JupyterLab. If you are working with compute-intensive data science models that require GPU support, use the Compute Unified Device Architecture (CUDA) notebook image to gain access to the NVIDIA CUDA Toolkit. You can optimize your work using GPU-accelerated libraries and optimization tools using this toolkit.

[2023b Packages](https://github.com/opendatahub-io/notebooks/blob/2023b/jupyter/minimal/ubi9-python-3.9/Pipfile) || [2023a Packages](https://github.com/opendatahub-io/notebooks/blob/2023a/jupyter/minimal/ubi9-python-3.9/Pipfile) 


## Jupyter Data Science

Standard Data Science provides a browser-based integrated development environment where you can write, edit, and debug code using the familiar interface and features of JupyterLab. Use the Standard Data Science notebook image for models that do not require TensorFlow or PyTorch.  
This image contains commonly used libraries to assist you in developing your machine-learning models. Furthermore, we have integrated several useful libraries and applications. Notably, we've included **Mesa-libgl**, an additional library designed for OpenCV tasks. We've also introduced **Git-lfs**, which provides an efficient solution for handling large files, such as audio samples, videos, datasets, and graphics. The integration of **unixODBC** offers a standardized API for accessing data sources, including SQL Servers and other data sources with ODBC drivers. Lastly, the addition of **Libsndfile** makes it easier to read and write files containing sampled audio data. Additionally, this notebook comes equipped with standard **database clients** for MySQL, PostgreSQL, MSSQL, and MongoDB.

**NOTE:** All notebooks derived from the Jupyter Data Science Notebook inherit these libraries and applications, with the exception of the minimal and CUDA variants.

[2023b Packages](https://github.com/opendatahub-io/notebooks/blob/2023b/jupyter/datascience/ubi9-python-3.9/Pipfile) || [2023a Packages](https://github.com/opendatahub-io/notebooks/blob/2023a/jupyter/datascience/ubi9-python-3.9/Pipfile)

## Jupyter Tensorflow 

TensorFlow is an open-source platform for machine learning. It provides a browser-based integrated development environment where you can write, edit, and debug code using the familiar interface and features of JupyterLab.  With TensorFlow, you can build, train and deploy your machine learning models. TensorFlow contains advanced data visualization features, such as computational graph visualizations. It also allows you to easily monitor and track the progress of your models.

[2023b Packages](https://github.com/opendatahub-io/notebooks/blob/2023b/jupyter/tensorflow/ubi9-python-3.9/Pipfile) || [2023a Packages](https://github.com/opendatahub-io/notebooks/blob/2023a/jupyter/tensorflow/ubi9-python-3.9/Pipfile) 

## Jupyter PyTorch 

PyTorch is an open-source machine learning library optimized for deep learning. If you are working with computer vision or natural language processing models, use the Pytorch notebook image. It provides a browser-based integrated development environment where you can write, edit, and debug code using the familiar interface and features of JupyterLab.

[2023b Packages](https://github.com/opendatahub-io/notebooks/blob/2023b/jupyter/pytorch/ubi9-python-3.9/Pipfile) || [2023a Packages](https://github.com/opendatahub-io/notebooks/blob/2023a/jupyter/pytorch/ubi9-python-3.9/Pipfile)

## Jupyter TrustyAI

Use the TrustyAI notebook image to leverage your data science work with model explainability, tracing and accountability, and runtime monitoring. It provides a browser-based integrated development environment where you can write, edit, and debug code using the familiar interface and features of JupyterLab.

[2023b Packages](https://github.com/opendatahub-io/notebooks/blob/2023b/jupyter/trustyai/ubi9-python-3.9/Pipfile) || [2023a Packages](https://github.com/opendatahub-io/notebooks/blob/2023a/jupyter/trustyai/ubi9-python-3.9/Pipfile) 

 ## code-server

code-server provides a browser-based integrated development environment (IDE) where you can write, edit, and debug code using the familiar interface and features of code-server. It is particularly useful for collaborating with team members, as everyone can access the same development environment from their own devices.



## RStudio Server

It provides a powerful integrated development environment specifically designed for R programming. By integrating RStudio Server IDE into ODH, you equip data analysts with a dedicated environment for exploring and manipulating data, building models, and generating insightful visualizations. Moreover, If you are working with compute-intensive data science models that require GPU support, use the CUDA RStudio Server notebook image to gain access to the NVIDIA CUDA Toolkit. 



  
  
[Previous Page](https://github.com/opendatahub-io/notebooks/wiki) | [Next Page](https://github.com/opendatahub-io/notebooks/wiki/Developer-Guide)
  


