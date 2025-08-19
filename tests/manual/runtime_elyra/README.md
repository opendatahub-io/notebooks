# Runtime images testing

## Testing notebook runtime images with Elyra

# Table of contents

[**Overview	2**](#overview)

[**Elyra Testing	2**](#elyra-testing)

[**Setup AWS Credentials	3**](#setup-aws-credentials)

[**Pipeline setup	5**](#pipeline-setup)

[**Workbench creation	7**](#workbench-creation)

[**Pipeline testing	10**](#pipeline-testing)

## **Overview** {#overview}

Elyra enhances JupyterLab with AI-centric features, streamlining AI model development, debugging, and deployment for machine learning engineers and data scientists. It provides a visual pipeline editor for machine learning workflows, reusable code snippets, and Git integration for robust version control. Consistent environments are facilitated by runtime images, which also offer enhanced debugging capabilities, improved resource management, and seamless data source integration.

The Notebooks team is responsible for maintaining these runtime container images. This ensures Elyra pipelines can be executed using RHOAI images specifically crafted for this purpose, including accelerator support (NVIDIA and AMD GPUs), AI frameworks (pre-installed PyTorch and TensorFlow) and Python support**.**

This ensures ML engineers can focus on AI model development with reliable and efficient pipeline execution in RHOAI.

## **Elyra Testing** {#elyra-testing}

Elyra comes with a handful of plugins, but for the Notebooks team testing, we must only configure the AWS S3 bucket for the pipeline execution (as it saves data to buckets). No other plugins need to be tested by the Notebook team besides the runtime images and its basic workflow.

## Setup AWS Credentials {#setup-aws-credentials}

To properly configure your RHOAI project to have access to your Amazon AWS S3 bucket, we need to create a connection in RHOAI with the credentials, as follows:

1. After you created a data science project in RHOAI, open it and click on “Connections”:

   ![][image1]

2. Click on the “Create Connection” button, at the center of the screen:

   ![][image2]

3. After you gathered the credentials with your team, proceed with the creation of the connection with the following example:

   	**Step 1:**
   	**Connection type:** S3 compatible object storage \- v1

   	**Step 2:**
   	**Connection name:** aws
   	**Access key:** {fill with the access-key}
   	**Secret key:** {fill with the secret}
   	**Endpoint:** https://s3.amazonaws.com/
   	**Region:** us-east-1
   	**Bucket:** {fill-with-a-name-for-your-bucket}

| If you see an error on the pipeline creation, please, use one of the default S3 buckets |
| :---: |

4. Click on the “Create” button to create your connection

5. Check if the connection has been properly created:

   ![][image3]

## Pipeline setup {#pipeline-setup}

To properly configure your RHOAI project to run Elyra pipelines, we need to create a pipeline and configure it to use the AWS credentials created in the section above:

1. After you created your connection with your AWS credentials, click on the “Pipelines” tab:

   ![][image4]

2. Click on the “Configure pipeline server” button:

   ![][image5]

3. Click on the “Autofill from connection” dropdown, select the “aws” connection and click on the “Configure pipeline server” button:

   ![][image6]

4. Now, wait until the pipeline has been properly configured \- it might take a couple of minutes:

   ![][image7]

## Workbench creation {#workbench-creation}

To run Elyra pipelines, you need to create a data science cluster workbench in RHOAI, which will already contain Elyra installed on JupyterLab and available for use.

1. Go to the Workbenches tab in your RHOAI project:

   ![][image8]

2. Click on the “Create workbench” button:

   ![][image9]

3. On the workbench creation form, you can put any name you want, but it needs to be, at least, the data science image (you can choose the TensorFlow, PyTorch, among other images \- click [here](https://github.com/search?q=repo%3Aopendatahub-io%2Fnotebooks+COPY+%2F%24%7BDATASCIENCE_SOURCE_CODE%7D%5C%2Fsetup-elyra.sh%2F&type=code) for full list of images with Elyra):

   	**Name:** elyra-wb
   	**Image Selection:** Jupyter | Data Science | CPU | Python 3.12
   	**Container size:** Small
   	**Accelerator:** None
   	**Storage:** 2 GB (the workbench does not need all the default 20GB)

4. Click on the “Create workbench” button

5. Wait until your workbench is properly created:

   ![][image10]

6. Once your workbench is created and the status is changed to “Running”, click on the workbench name to open it in a new tab:

   ![][image11]

7. Once your JupyterLab opens, you can see that it has a section for Elyra:

   ![][image12]

## Pipeline testing {#pipeline-testing}

With Elyra, you can simply go and click to create your pipeline from scratch, or you can use JupyterLab's git clone functionality to pull a project from GitHub / GitLab / etc and run the pipeline from this repository directly.

In this testing scenario, we will use a [sample Elyra application available on GitHub](https://github.com/harshad16/data-science-pipeline-example) to test a runtime image and see if the pipeline executes properly.

1. In JupyterLab, click on the Git Clone button, on the left menu:

   ![][image13]

2. On the “Clone a repo” dialog, fill in the the sample application's HTTPS link and click on “Clone”:

   ![][image14]

3. Once the repository has been downloaded, you can navigate through the folders on the left. Let's go to the Iris folder:

   ![][image15]

4. A new window will be launched inside JupyterLab and you can see the Iris application's pipeline on it:

   ![][image16]

5. From each one of these blocks, if you click on them, you can select which runtime image will be used to run the pipeline:

   ![][image17]

6. Once you have chosen the runtime image for all pipeline scripts, press the “Play” button in the top menu to execute the pipeline:

   ![][image18]

7. Fill in with a name for your pipeline execution and press the “OK” button in the dialog:

   ![][image19]

8. Wait until your pipeline starts

   ![][image20]

9. Click on the “Run Details” link to follow up your pipeline execution:

   ![][image21]

10. You can also see the progress from your RHOAI dashboard and clicking in the “Experiments \> Experiments and runs” menu:

    ![][image22]

11. If your pipeline succeeds in the execution, then your runtime images are working as expected and the test is good.

[image1]: images/img_001_540124f9328693a1.png
[image2]: images/img_002_a67649a3481921a0.png
[image3]: images/img_003_93b2f00a24a50ba5.png
[image4]: images/img_004_f6fb213b7c025110.png
[image5]: images/img_005_79f45424b074b771.png
[image6]: images/img_006_54fbd228f8a42606.png
[image7]: images/img_007_a6379b0293c51668.png
[image8]: images/img_008_98637cabac3e7dc0.png
[image9]: images/img_009_9383a8eeecdb4f05.png
[image10]: images/img_010_ab640941c0b73fd9.png
[image11]: images/img_011_6a98825cc08b7287.png
[image12]: images/img_012_415f8c4792ae6f30.png
[image13]: images/img_013_7b7d198ba42ecbf7.png
[image14]: images/img_014_d319253a7b58e7af.png
[image15]: images/img_015_f0ea7c430c130289.png
[image16]: images/img_016_7cabbcc983333981.png
[image17]: images/img_017_e402e2ff16aec9ef.png
[image18]: images/img_018_f544d157b449cbde.png
[image19]: images/img_019_9b2fd9d3d3ab3a31.png
[image20]: images/img_020_4279d51e65f85947.png
[image21]: images/img_021_677be6ce28801bad.png
[image22]: images/img_022_659e781dc93b07bf.png
