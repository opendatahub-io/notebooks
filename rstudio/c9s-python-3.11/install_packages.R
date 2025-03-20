# install_packages.R

# Load or install 'remotes' package
if (!requireNamespace("remotes", quietly = TRUE)) {
    install.packages("remotes")
}

# Install specific versions of packages
remotes::install_version('Rcpp', '1.0.14')
remotes::install_version('tidyverse', '2.0.0')
remotes::install_version('tidymodels', '1.3.0')
remotes::install_version('plumber', '1.3.0')
remotes::install_version('vetiver', '0.2.5')
remotes::install_version('devtools', '2.4.5')