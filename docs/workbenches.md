
Workbench images are supported for a minimum of one year. Major updates to pre-configured notebook images occur approximately every six months. Therefore, two supported notebook images are typically available at any given time. If necessary, you can still access older notebook images from the registry, even if they are no longer supported. You can then add the older notebook images as custom notebook images to cater to the project’s specific requirements.

Open Data Hub contains the following workbench images with different variations:

| Workbenches          | ODH | RHODS | OS     | GPU | Runtimes |
|----------------------|-----|-------|--------|-----|----------|
| Jupyter Minimal      |  V  | V     | UBI8/9 | -   | -        |
| CUDA                 | V   | V     | UBI8/9 | V   | -        |
| Jupyter Data Science | V   | V     | UBI8/9 | -   | V        |
| Jupyter Tensorflow   | V   | V     | UBI8/9 | V   | V        |
| Jupyter PyTorch      | V   | V     | UBI8/9 | V   | V        |
| Jupyter TrustyAI     | V   | V     | UBI9   | -   | -        |
| Code Server          | V   | -     | C9S    | -   | -        |
| R Studio             | V   | -     | C9S    | V   | -        |

These notebooks are incorporated to be used in conjunction with Open Data Hub, specifically utilizing the ODH Notebook Controller as the launching platform.

## Jupyter Minimal

If you do not require advanced machine learning features or additional resources for compute-intensive data science work, you can use the Minimal Python image to develop your models.

[Installed Packages](https://github.com/opendatahub-io/notebooks/blob/main/jupyter/minimal/ubi9-python-3.9/Pipfile)


## CUDA

If you are working with compute-intensive data science models that require GPU support, use the Compute Unified Device Architecture (CUDA) notebook image to gain access to the NVIDIA CUDA Toolkit. Using this toolkit, you can optimize your work using GPU-accelerated libraries and optimization tools.

[Installed Packages](https://github.com/opendatahub-io/notebooks/blob/main/jupyter/minimal/ubi9-python-3.9/Pipfile)

## Jupyter Data Science

Use the Standard Data Science notebook image for models that do not require TensorFlow or PyTorch. This image contains commonly used libraries to assist you in developing your machine-learning models. 	

[Installed Packages](https://github.com/opendatahub-io/notebooks/blob/main/jupyter/datascience/ubi9-python-3.9/Pipfile)

## Jupyter Tensorflow 

TensorFlow is an open-source platform for machine learning. With TensorFlow, you can build, train and deploy your machine learning models. TensorFlow contains advanced data visualization features, such as computational graph visualizations. It also allows you to easily monitor and track the progress of your models.

[Installed Packages](https://github.com/opendatahub-io/notebooks/blob/main/jupyter/tensorflow/ubi9-python-3.9/Pipfile)

## Jupyter PyTorch 

PyTorch is an open-source machine learning library optimized for deep learning. If you are working with computer vision or natural language processing models, use the Pytorch notebook image. 	

[Installed Packages](https://github.com/opendatahub-io/notebooks/blob/main/jupyter/pytorch/ubi9-python-3.9/Pipfile)

## Jupyter TrustyAI

Use the TrustyAI notebook image to leverage your data science work with model explainability, tracing and accountability, and runtime monitoring. 	

[Installed Packages](https://github.com/opendatahub-io/notebooks/blob/main/jupyter/trustyai/ubi9-python-3.9/Pipfile)

 ## Code Server

Code Server (VS Code) provides a browser-based integrated development environment (IDE) where you can write, edit, and debug code using the familiar interface and features of VS Code. It is particularly useful for collaborating with team members, as everyone can access the same development environment from their own devices. In order to unlock the code server notebook is required to enable the additional overlay layer on the kfdef.

## R Studio

It provides a powerful integrated development environment specifically designed for R programming. By integrating R Studio IDE into ODH, you equip data analysts with a dedicated environment for exploring and manipulating data, building models, and generating insightful visualizations. Moreover, If you are working with compute-intensive data science models that require GPU support, use the CUDA R Studio notebook image to gain access to the NVIDIA CUDA Toolkit. In order to unlock the R Studio notebook is required to enable the additional overlay layer on the kfdef.

  
  
[Previous Page](https://github.com/opendatahub-io/notebooks/wiki) | [Next Page](https://github.com/opendatahub-io/notebooks/wiki/Developer-Guide)
  


