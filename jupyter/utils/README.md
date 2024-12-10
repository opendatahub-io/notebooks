# Shared files for all JupyterLab workbenches we have

These files were initially duplicated into many `jupyter/` subdirectories.
In general, they are incorporated into every JupyterLab workbench,
but sometimes that's through building `FROM` base `datascience` image and not `COPY`ed directly.
