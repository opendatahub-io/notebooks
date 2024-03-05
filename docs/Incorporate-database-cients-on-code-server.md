# Incorporate standard database clients on code-server

## Introduction

In the field of Database Management Systems effective interaction is crucial for developers. Incorporating standard database clients directly into your code-server environment can streamline your workflow, offering a seamless interface for managing databases. This tutorial will walk you through the process of incorporating different Database Management System clients into code-server, whether through built-in extensions within code-server or by creating your own custom image.

## 1. Through Extensions

### Installation Guide

1.  Open the code-server workbench and navigate to the Extensions view.
    
2.  Search for the desired extension using the provided recommended links.
    
3.  Click "Install" to add the extension to your code-server environment.
    
### Recommended extensions list

**MongoDB for code-server**

MongoDB for code-server empowers you to connect to MongoDB and Atlas directly from your code-server environment. Explore databases and collections, inspect schemas, and prototype queries and aggregations effortlessly using the integrated playgrounds.

[Link to Extension](https://marketplace.visualstudio.com/items?itemName=mongodb.mongodb-vscode)

**MySQL Shell for code-server**

This extension provides a robust MySQL Shell for code-server, enhancing your capability to manage MySQL databases seamlessly within the code-server environment.

[Link to Extension](https://marketplace.visualstudio.com/items?itemName=Oracle.mysql-shell-for-vs-code)

**SQL Server (MSSQL)**

Connect to SQL Server effortlessly with this extension, enabling you to perform database tasks directly from your code-server workspace.

[Link to Extension](https://marketplace.visualstudio.com/items?itemName=ms-mssql.mssql)

**PostgreSQL**

This extension facilitates direct interaction with PostgreSQL databases, allowing you to navigate, query, and manage your PostgreSQL instances efficiently.

[Link to Extension](https://marketplace.visualstudio.com/items?itemName=ms-ossdata.vscode-postgresql)

**SQLTools**

SQLTools simplifies database connections, supporting a wide array of commonly used databases. This extension enhances data management and query execution, making it an invaluable tool for developers.

[Link to Extension](https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools)

**Database Client**

This versatile extension serves as a database manager for MySQL/MariaDB, PostgreSQL, SQLite, Redis, and ElasticSearch. It provides a unified interface for managing diverse databases within the code-server environment.

[Link to Extension](https://marketplace.visualstudio.com/items?itemName=cweijan.vscode-database-client2)

# 2. Through Custom Image

Custom notebook images are a powerful tool when working with containerized environments, especially in scenarios where you need specific libraries, OS packages, or applications that are not readily available in base images. This tutorial will guide you through the process of creating a custom notebook image with Database Management System (DBMS) clients using Dockerfile.

## Prerequisites  

Before you begin, make sure you have Docker installed on your system.

**Step 1: Clone the Repository**

Start by cloning the Open Data Hub notebooks repository:

```git clone git@github.com:opendatahub-io/notebooks.git```

**Step 2: Create a New Dockerfile**

Navigate to the codeserver folder and create a new folder for your custom image. For example, let's name it ubi9-python-3.9-db-clients. Inside this folder, create a Dockerfile with the following instructions:
 
```
# The base image auto assigned by the make recipe from the next step, in this case is the code-server notebook.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

WORKDIR /opt/app-root/bin

# Install OS packages as root
USER root

# Install necessary OS packages
RUN dnf install -y unixODBC postgresql

# Install MongoDB Client
COPY mongodb-org-6.0.repo-x86_64 /etc/yum.repos.d/mongodb-org-6.0.repo

RUN dnf install -y mongocli

# Install MSSQL Client
COPY mssql-2022.repo-x86_64 /etc/yum.repos.d/mssql-2022.repo

RUN ACCEPT_EULA=Y dnf install -y mssql-tools18 unixODBC-devel

ENV PATH="$PATH:/opt/mssql-tools18/bin"

# Switch back to default user
USER 1001

WORKDIR /opt/app-root/src
```
  
**Step 3: Add RPM Files**

Create two RPM files, mongodb-org-6.0.repo-x86_64 and mssql-2022.repo-x86_64, in the folder you created earlier. The content for these files is provided in the tutorial.  
  
Filename: mongodb-org-6.0.repo-x86_64

```
[mongodb-org-6.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/9/mongodb-org/6.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-6.0.asc  
```
  
Filename: mssql-2022.repo-x86_64

```
[packages-microsoft-com-prod]
name=packages-microsoft-com-prod
baseurl=https://packages.microsoft.com/rhel/9.0/prod/
enabled=1
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc
```
  
**Step 4: Build and Push the Image**

To streamline the build and push process, update the Makefile with a new recipe:

```
.PHONY: codeserver-ubi9-python-3.9-db-clients
codeserver-ubi9-python-3.9-db-clients: codeserver-ubi9-python-3.9
$(call image,$@,codeserver/ubi9-python-3.9-db-clients,$<)
```
  
Run the following command to build and push the image:

```
$ make codeserver-ubi9-python-3.9-db-clients -e IMAGE_REGISTRY=quay.io/${YOUR_USERNAME}/workbench-images
```
 
Note: Replace `${YOUR_USERNAME}` with your actual username, and the registry can be any valid registry, not just quay.io.

**Step 5: Import Custom Image into ODH/RHOAI**

After pushing the custom image, import it into Red Hat OpenAI through the admin panel:

Navigate to `Settings -> Notebooks Image Settings -> Import New Image`.

**Step 6: Use Custom Image in a Data Science Project**

Create or open a Data Science Project, create a new workbench, and select the custom image from the Image Selection dropdown.

**Step 7: Verify Database Clients Installation**

Open a new terminal inside the code-server and run the following command to ensure successful installation of database clients:

`$ yum list installed | grep -E 'mssql|mongo|postgresql'`

If everything is set up correctly, you should see a list of installed packages related to MongoDB, MSSQL, and PostgreSQL.  
  
Here you may find an example: [https://github.com/atheo89/notebooks/tree/add-db-clients-example/codeserver/ubi9-python-3.9-plus](https://github.com/atheo89/notebooks/tree/add-db-clients-example/codeserver/ubi9-python-3.9-plus)
