# Workbench Images Updates

## Overview
This document aims to provide an overview of the rebuilding plan for the notebook images. There are two types of updates that are implemented:

1.  *Release updates* - These updates will be carried out twice a year and will incorporate major updates to the notebook images.

2.  *Patch updates* - These updates will be carried out weekly and will focus on incorporating security updates to the notebook images.

## Scope and frequency of the updates

When performing major updates to the notebook images, all components are reviewed for updates, including the base OS image, OS packages, Python version, and Python packages and libraries. A major update, which will be named “YYYYx” release (where YYYY is the year and x is an increased letter), will fix the set of components that are included, as well as their MAJOR and MINOR versions.

During the release lifecycle, which is the period during which the update is supported, the only updates that will be made are patches to allow for security updates and fixes while maintaining compatibility. These weekly updates will only modify the PATCH version, leaving the major and minor versions unchanged.

## Naming Convention for Notebook Images

To ensure consistency in naming of the notebook images, we are using the convention 'workbench-images:image-name-tag'. Where, the "image-name" segment should indicate the image's type/flavor, along with its OS version and Python version (e.g., jupyter-datascience-ubi8-python-3.8), and the "tag" segment should include the release name and patch version for easy identification. For clarity, we suggest using a YearIndex scheme for the release (e.g., 2023a) and incorporating the patch's date and weekly tag in the YYYYMMDD format.

For instance, "*workbench-images:jupyter-datascience-ubi9-python-3.9-2023a-20230115*" refers to the Jupyter Standard Data Science image based on UBI9, using Python 3.9, with a set of components as defined in release 2023a. This image is fully patched as of January 15, 2023. Additionally, "*workbench-images:jupyter-datascience-ubi9-python-3.9-2023a-weekly*" denotes the most recent version of the image.

## Support

Our goal is to ensure that notebook images are supported for a minimum of one year, meaning that typically two supported images will be available at any given time. This provides sufficient time for users to update their code to use components from the latest notebook images. We will continue to make older images available in the registry for users to add as custom notebook images, even if they are no longer supported. This way, users can still access the older images if needed.

Example lifecycle (not actual dates):

-   2023-01-01 - only one version of the notebook images available - version 1 for all images.
-   2023-06-01 - release updated images - version 2 (v2023a). Versions 1 & 2 are supported and available for selection in the UI.
-   2023-12-01 - release updated images - version 3 (v2023b). Versions 2 & 3 are supported and available for selection in the UI.
-   2024-06-01 - release updated images - version 4 (v2024a). Versions 3 & 4 are supported and available for selection in the UI.
