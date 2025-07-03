#!/bin/sh
set -ex
# Replace PyTorch's vendored shared libraries with system libraries
# The script assumes that PyTorch is built with the same ROCm ABI as the
# system installation of ROCm.

# Source: https://github.com/tiran/instructlab-containers/blob/main/containers/rocm/de-vendor-torch.sh

PYTHON=python3.12
ROCMLIB=/opt/rocm/lib
TORCHLIB=/opt/app-root/lib/${PYTHON}/site-packages/torch/lib

ln -sf /usr/lib64/libdrm.so.2 ${TORCHLIB}/libdrm.so
ln -sf /usr/lib64/libdrm_amdgpu.so.1 ${TORCHLIB}/libdrm_amdgpu.so

ln -sf ${ROCMLIB}/libamd_comgr.so.2 ${TORCHLIB}/libamd_comgr.so
ln -sf ${ROCMLIB}/libamdhip64.so.6 ${TORCHLIB}/libamdhip64.so
ln -sf ${ROCMLIB}/libhipblaslt.so.0 ${TORCHLIB}/libhipblaslt.so
ln -sf ${ROCMLIB}/libhipblas.so.2 ${TORCHLIB}/libhipblas.so
ln -sf ${ROCMLIB}/libhipfft.so.0 ${TORCHLIB}/libhipfft.so
ln -sf ${ROCMLIB}/libhiprand.so.1 ${TORCHLIB}/libhiprand.so
ln -sf ${ROCMLIB}/libhiprtc.so.6 ${TORCHLIB}/libhiprtc.so
ln -sf ${ROCMLIB}/libhipsolver.so.0 ${TORCHLIB}/libhipsolver.so
ln -sf ${ROCMLIB}/libhipsparse.so.1 ${TORCHLIB}/libhipsparse.so
ln -sf ${ROCMLIB}/libhsa-runtime64.so.1 ${TORCHLIB}/libhsa-runtime64.so
ln -sf ${ROCMLIB}/libMIOpen.so.1 ${TORCHLIB}/libMIOpen.so
ln -sf ${ROCMLIB}/librccl.so.1 ${TORCHLIB}/librccl.so
ln -sf ${ROCMLIB}/librocblas.so.4 ${TORCHLIB}/librocblas.so
ln -sf ${ROCMLIB}/librocfft.so.0 ${TORCHLIB}/librocfft.so
ln -sf ${ROCMLIB}/librocm_smi64.so.6 ${TORCHLIB}/librocm_smi64.so
ln -sf ${ROCMLIB}/librocrand.so.1 ${TORCHLIB}/librocrand.so
ln -sf ${ROCMLIB}/librocsolver.so.0 ${TORCHLIB}/librocsolver.so
ln -sf ${ROCMLIB}/librocsparse.so.1 ${TORCHLIB}/librocsparse.so
ln -sf ${ROCMLIB}/libroctracer64.so.4 ${TORCHLIB}/libroctracer64.so
ln -sf ${ROCMLIB}/libroctx64.so.4 ${TORCHLIB}/libroctx64.so

rm -rf ${TORCHLIB}/rocblas
ln -sf ${ROCMLIB}/rocblas ${TORCHLIB}/rocblas

rm -rf ${TORCHLIB}/hipblaslt
ln -sf ${ROCMLIB}/hipblaslt ${TORCHLIB}/hipblaslt
