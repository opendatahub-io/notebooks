## RStudio Server User Guide

### Introduction

RStudio Server is a versatile and comprehensive open-source Integrated Development Environment (IDE) widely utilized as a graphical interface for R programming. It provides an array of valuable features, including robust support for reproducible analyses through R Markdown vignettes. These vignettes enable users to seamlessly integrate text with code in R, Python, Julia, shell scripts, SQL, Stan, JavaScript, C, C++, Fortran, and more, similar to Jupyter Notebooks. With a user-friendly interface, RStudio facilitates the creation and storage of reusable scripts, project management for efficient organization and collaboration, seamless switching between terminal and console environments, tracking of operational history, and a host of other functionalities.

By integrating R Studio Server into Open Data Hub, you equip data analysts with a dedicated environment for exploring and manipulating data, building models, and generating insightful visualizations. Moreover, If you are working with compute-intensive data science models that require GPU support, use the CUDA R Studio Server workbench to gain access to the NVIDIA CUDA Toolkit.  

### Launch RStudio Server

To launch RStudio Server, there are two methods available:

The first method involves accessing the Notebooks workbench spawner page:

1.  Navigate to Applications and click on Enabled.
2.  Locate the JupyterHub card and click Launch.
3.  A new browser tab will open, presenting several notebooks. Select RStudio Server Workbench.  
      
The second method utilizes Data Science Projects:

1.  Click the blue button labeled "Create data science project."
2.  In the Workbenches section, specify the desired name.
3.  From the Dropdown list, locate and select RStudio Server Workbench.
4.  Press the Create Workbench button on the bottom of the page.
5.  Once the status changes from "Starting" to "Running," your notebook is ready for use.  

Now that we've effectively spawned RStudio Server, let's delve into its primary features, and explore various operations.

Here's how the platform interface appears:  
  
![](https://lh7-us.googleusercontent.com/OgSEc8I-VpWtegFWGG36UP6lhHrj6yGCVq5IXadytEL8cMRvJbJHBlifZXn31-YTgRKnjfNvPkSRQme5tM5sLEzVNpJ6lhfHJtMdTk1ihqv85Jt_ONbrg41LpLt2n_ikNF3pfM8cgdzRSCQTsiRl1_w)
  

Let's examine key working areas:
  
**Console**:

The Console tab provides information about the current R version and offers a set of basic commands to experiment with. Here, you can perform a variety of tasks typically done in R programs, such as installing packages, executing mathematical operations, assigning variables, and importing data. However, keep in mind that code executed directly in the console isn't automatically saved for future use. For reproducible tasks, it's best to write and save code in a script file.

**Environment**:

Variables and their values are stored as objects in the workspace, displayed in the Environment tab. When you define or reassign a variable in RStudio, it appears here. Try an example like sum <- 3 + 5 in the console to see it reflected in the Environment tab.

**Other important tabs**:

**Terminal**: Utilize this tab to run commands from the terminal.

**History**: Tracks all operations performed during the current RStudio session.

**Files**: Navigate the working folder's structure, reset the folder, and manage file tasks.

**Plots**: Preview and export data visualizations created in R.

**Packages**: Check loaded packages and manage their loading/unloading status.  
  
### Perform Various Operations

This section will explore the actions available in RStudio for data analysis purposes. Essentially, the operations we'll cover are not exclusive to RStudio but are applicable to using R in any integrated development environment (IDE).  
  
**Write R Scripts**  

To ensure the reproducibility and reusability of your code for future purposes, it's advisable to write it in a script file instead of directly in the console. To begin creating a script, navigate to File → New File → R Script. This action will open a text editor in the top-left corner of the RStudio interface.  
  
**Installing R Packages**  
  
It is recommended to install the packages directly in the console instead of within a script file, as they only need to be installed on the hard disk once.

The syntax for a package installation is: `install.packages("package_name")`.

Once the package is installed, you can load it into the R environment using the `library()` function.

Alternatively, you have the option to install packages directly from the RStudio Server interface. Simply open the Packages tab (located in the bottom-left area), click Install, and then select the required packages from CRAN, separating them with either a space or a comma.