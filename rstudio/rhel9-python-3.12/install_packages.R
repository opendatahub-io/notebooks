# install_packages.R

# Configure CRAN mirror and user library (aligns with rsession.conf 4.5)
options(repos = c(CRAN = Sys.getenv("R_CRAN_MIRROR", "https://cloud.r-project.org")))
lib <- Sys.getenv("R_LIBS_USER", "/opt/app-root/src/Rpackages/4.5")
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(lib, .libPaths()))
options(Ncpus = as.integer(Sys.getenv("R_COMPILE_NCPUS", 2L)))

# Load or install 'remotes' package
if (!requireNamespace("remotes", quietly = TRUE)) {
    install.packages("remotes")
}

# Install specific versions of packages
remotes::install_version('Rcpp',       '1.0.14', lib = lib, dependencies = TRUE, upgrade = "never")
remotes::install_version('tidyverse',  '2.0.0',  lib = lib, dependencies = TRUE, upgrade = "never")
remotes::install_version('tidymodels', '1.4.1',  lib = lib, dependencies = TRUE, upgrade = "never")
remotes::install_version('vetiver',    '0.2.5',  lib = lib, dependencies = TRUE, upgrade = "never")
remotes::install_version('devtools',   '2.4.5',  lib = lib, dependencies = TRUE, upgrade = "never")
