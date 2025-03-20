/usr/bin/env bash
set -Eeuo pipefail

# GitHub Actions runners have two disks, /dev/root and /dev/sda1.
# We would like to be able to combine available disk space on both and use it for podman container builds.
#
# This script creates file-backed volumes on /dev/root and /dev/sda1, then creates ext4 over both, and mounts it for our use
# https://github.com/easimon/maximize-build-space/blob/master/action.yml

# root_reserve_mb=2048 was running out of disk space building cuda images
root_reserve_mb=4096
temp_reserve_mb=100
swap_size_mb=256

build_mount_path="${HOME}/.local/share/containers"
build_mount_path_ownership="runner:runner"

pv_loop_path=/pv.img
tmp_pv_loop_path=/mnt/tmp-pv.img
overprovision_lvm=false

VG_NAME=buildvg

# github runners have an active swap file in /mnt/swapfile
# we want to reuse the temp disk, so first unmount swap and clean the temp disk
echo "Unmounting and removing swap file."
sudo swapoff -a
sudo rm -f /mnt/swapfile

echo "Creating LVM Volume."
echo "  Creating LVM PV on root fs."
# create loop pv image on root fs
ROOT_RESERVE_KB=$(expr ${root_reserve_mb} \* 1024)
ROOT_FREE_KB=$(df --block-size=1024 --output=avail / | tail -1)
ROOT_LVM_SIZE_KB=$(expr $ROOT_FREE_KB - $ROOT_RESERVE_KB)
ROOT_LVM_SIZE_BYTES=$(expr $ROOT_LVM_SIZE_KB \* 1024)
sudo touch "${pv_loop_path}" && sudo fallocate -z -l "${ROOT_LVM_SIZE_BYTES}" "${pv_loop_path}"
export ROOT_LOOP_DEV=$(sudo losetup --find --show "${pv_loop_path}")
sudo pvcreate -f "${ROOT_LOOP_DEV}"

# create pv on temp disk
echo "  Creating LVM PV on temp fs."
TMP_RESERVE_KB=$(expr ${temp_reserve_mb} \* 1024)
TMP_FREE_KB=$(df --block-size=1024 --output=avail /mnt | tail -1)
TMP_LVM_SIZE_KB=$(expr $TMP_FREE_KB - $TMP_RESERVE_KB)
TMP_LVM_SIZE_BYTES=$(expr $TMP_LVM_SIZE_KB \* 1024)
sudo touch "${tmp_pv_loop_path}" && sudo fallocate -z -l "${TMP_LVM_SIZE_BYTES}" "${tmp_pv_loop_path}"
export TMP_LOOP_DEV=$(sudo losetup --find --show "${tmp_pv_loop_path}")
sudo pvcreate -f "${TMP_LOOP_DEV}"

# create volume group from these pvs
sudo vgcreate "${VG_NAME}" "${TMP_LOOP_DEV}" "${ROOT_LOOP_DEV}"

echo "Recreating swap"
# create and activate swap
sudo lvcreate -L "${swap_size_mb}M" -n swap "${VG_NAME}"
sudo mkswap "/dev/mapper/${VG_NAME}-swap"
sudo swapon "/dev/mapper/${VG_NAME}-swap"

echo "Creating build volume"
# create and mount build volume
sudo lvcreate --type raid0 --stripes 2 --stripesize 4 --alloc anywhere --extents 100%FREE --name buildlv "${VG_NAME}"
if [[ ${overprovision_lvm} == 'true' ]]; then
  sudo mkfs.ext4 -m0 "/dev/mapper/${VG_NAME}-buildlv"
else
  sudo mkfs.ext4 -Enodiscard -m0 "/dev/mapper/${VG_NAME}-buildlv"
fi
mkdir -p "${build_mount_path}"
# https://www.alibabacloud.com/help/en/ecs/use-cases/mount-parameters-for-ext4-file-systems?spm=a2c63.p38356.help-menu-25365.d_5_10_12.48ce3be5RixoUB#8e740ed072m5o
sudo mount -o defaults,noatime,nodiratime,nobarrier,nodelalloc,data=writeback "/dev/mapper/${VG_NAME}-buildlv" "${build_mount_path}"
sudo chown -R "${build_mount_path_ownership}" "${build_mount_path}"

# if build mount path is a parent of $GITHUB_WORKSPACE, and has been deleted, recreate it
if [[ ! -d "${GITHUB_WORKSPACE}" ]]; then
  sudo mkdir -p "${GITHUB_WORKSPACE}"
  sudo chown -R "${WORKSPACE_OWNER}" "${GITHUB_WORKSPACE}"
fi
