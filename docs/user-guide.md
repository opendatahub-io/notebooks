The following sections are aimed to provide a comprehensive guide on effectively utilizing an out-of-the-box notebook by a user.
There are two options for launching a workbench image: either through the Enabled applications or the Data Science Project.

## Notebook Spawner 

In the ODH dashboard, you can navigate to Applications -> Enabled -> Launch Application from the Jupyter tile. The notebook server spawner page displays a list of available container images you can run as a single user."

<p align="center">
<img src="https://github.com/opendatahub-io/notebooks/assets/42587738/8ff97ee4-4c47-4b87-b476-fe5adec4462d" data-canonical-src="https://github.com/opendatahub-io/notebooks/assets/42587738/8ff97ee4-4c47-4b87-b476-fe5adec4462d" width="700" height="950" />
</p>


## Data Science Project

A user can navigate to the Data Science Project menu and create a project like the following:

<p align="center">
<img src="https://github.com/opendatahub-io/notebooks/assets/42587738/487b99b0-01a4-4fb6-8f68-17b558c3808f" data-canonical-src="https://github.com/opendatahub-io/notebooks/assets/42587738/487b99b0-01a4-4fb6-8f68-17b558c3808f" width="950" height="920" />
</p>

## Updates

This section provides an overview of the rebuilding plan. There are two types of updates that are implemented:

1. Release updates - These updates will be carried out twice a year and incorporate major updates to the notebook images.
1. Patch updates - These updates will be carried out weekly and will focus on incorporating security updates to the notebook images.


**Scope and frequency of the updates**

When performing major updates to the notebook images, all components are reviewed for updates, including the base OS image, OS packages, Python version, and Python packages and libraries. A major update, which will be named “YYYYx” release (where YYYY is the year and x is an increased letter), will fix the set of components that are included, as well as their MAJOR and MINOR versions.
During the release lifecycle, which is the period during which the update is supported, the only updates that will be made are patches to allow for security updates and fixes while maintaining compatibility. These weekly updates will only modify the PATCH version, leaving the major and minor versions unchanged.

**Support**

Our goal is to ensure that notebook images are supported for a minimum of one year, meaning that typically two supported images will be available at any given time. This provides sufficient time for users to update their code to use components from the latest notebook images. We will continue to make older images available in the registry for users to add as custom notebook images, even if they are no longer supported. This way, users can still access the older images if needed.
Example lifecycle (not actual dates):

2023-01-01 - only one version of the notebook images is available - version 1 for all images.  
2023-06-01 - release updated images - version 2 (v2023a). Versions 1 & 2 are supported and available for selection in the UI.  
2023-12-01 - release updated images - version 3 (v2023b). Versions 2 & 3 are supported and available for selection in the UI.  
2024-06-01 - release updated images - version 4 (v2024a). Versions 3 & 4 are supported and available for selection in the UI.  


[Previous Page](https://github.com/opendatahub-io/notebooks/wiki/Developer-Guide)

