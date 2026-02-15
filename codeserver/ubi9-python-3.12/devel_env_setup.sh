#!/bin/bash
set -eoux pipefail

############################################################################################
# devel_env_setup.sh - Arch-specific setup for the whl-cache stage
#
# [HERMETIC] This script runs inside the whl-cache stage with --network=none.
#
# On all architectures: This script is effectively a no-op.
#
# All native Python packages (pyarrow, pillow, matplotlib, pyzmq, scipy,
# numpy, scikit-learn, pandas, contourpy, kiwisolver, onnx, etc.) use pre-built
# RHOAI wheels (prefetched by cachi2 from requirements-rhoai.txt). No Python
# source builds are needed for these packages.
#
# OpenBLAS (runtime dependency for numpy/scipy) is installed via the
# `openblas-threads` RPM, which provides the correct `libopenblasp.so.0`
# (pthreads variant) soname that the RHOAI numpy/scipy wheels link against.
# No source compilation needed.
############################################################################################
export WHEEL_DIR=${WHEEL_DIR:-"/wheelsdir"}
mkdir -p ${WHEEL_DIR}
