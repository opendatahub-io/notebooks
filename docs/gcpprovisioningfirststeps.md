# GCP Instance Provisioning: First Steps Guide

This guide covers essential first steps after provisioning a RHEL instance on Google Cloud Platform. Following these steps will prevent common issues like unresponsive SSH sessions, slow package management, and out-of-memory conditions.

## 1. Choose the Right Instance Size

### Avoid `e2-micro` for Development Work

The `e2-micro` instance type is **not suitable** for:
- Running package managers (dnf/yum)
- Container workloads
- Any development or testing work

**Why it fails:**
| Resource | e2-micro | Minimum Recommended |
|----------|----------|---------------------|
| vCPU | 0.25 (shared) | 0.5+ |
| RAM | 1 GB | 2 GB+ |
| Burst | Limited credits | Sustained |

DNF metadata operations alone can consume 500MB+ RAM, leaving the system unresponsive.

### Recommended Minimums

| Use Case | Instance Type | vCPU | RAM |
|----------|---------------|------|-----|
| Light testing | `e2-small` | 0.5 | 2 GB |
| Development | `e2-medium` | 1 | 4 GB |
| Container builds | `e2-standard-2` | 2 | 8 GB |
| ML/Heavy workloads | `n1-standard-4`+ | 4+ | 15 GB+ |

## 2. Configure Swap Space

GCP instances typically have **no swap configured by default**. This causes OOM kills under memory pressure.

### Create Swap File (Recommended: 2-4GB)

```bash
# Create a 4GB swap file
sudo fallocate -l 4G /swapfile

# Secure the file
sudo chmod 600 /swapfile

# Format as swap
sudo mkswap /swapfile

# Enable swap
sudo swapon /swapfile

# Verify
free -h
```

### Make Swap Persistent

```bash
# Add to fstab
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Verify fstab entry
cat /etc/fstab | grep swap
```

### Tune Swappiness (Optional)

For workloads that benefit from keeping more in RAM:

```bash
# Reduce swappiness (default is 60, lower = less eager to swap)
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.d/99-swappiness.conf
sudo sysctl -p /etc/sysctl.d/99-swappiness.conf
```

## 3. Optimize DNF Configuration

RHEL on GCP comes with many repositories enabled by default, including debug and source repos that most users don't need. This causes:
- **500+ MB of metadata downloads** on every refresh
- **123,000+ packages** to index
- Slow operations even on powerful machines

### Disable Unnecessary Repositories

```bash
# Disable debug RPM repos (only needed for gdb debugging)
sudo dnf config-manager --disable '*-debug-rpms'

# Disable source RPM repos (only needed for package rebuilding)
sudo dnf config-manager --disable '*-source-rpms'

# Verify what's enabled
dnf repolist --enabled
```

This typically reduces metadata from ~550MB to ~250MB.

### (Optional) Disable Google Cloud SDK Repo

If you don't use `gcloud` CLI tools frequently:

```bash
# The google-cloud-sdk repo has 155MB of metadata alone
sudo dnf config-manager --disable google-cloud-sdk

# You can still install gcloud manually when needed
```

### Optimize DNF Settings

```bash
# Edit DNF configuration
sudo tee -a /etc/dnf/dnf.conf << 'EOF'

# Performance optimizations
max_parallel_downloads=10
fastestmirror=True

# Reduce metadata refresh frequency (default: 48h)
metadata_expire=7d

# Show download progress
verbose=False
EOF
```

### Rebuild Cache

After configuration changes:

```bash
# Clear old cache
sudo dnf clean all

# Build new cache (will be much faster now)
sudo dnf makecache
```

## 4. Quick Setup Script

Combine all steps into a single script:

```bash
#!/bin/bash
set -euo pipefail

echo "=== GCP RHEL Instance Setup ==="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "Run this script with sudo"
   exit 1
fi

echo "[1/4] Creating swap file..."
if [[ ! -f /swapfile ]]; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "vm.swappiness=10" > /etc/sysctl.d/99-swappiness.conf
    sysctl -p /etc/sysctl.d/99-swappiness.conf
    echo "Swap configured: $(free -h | grep Swap)"
else
    echo "Swap file already exists"
fi

echo "[2/4] Disabling unnecessary repos..."
dnf config-manager --disable '*-debug-rpms' '*-source-rpms' 2>/dev/null || true

echo "[3/4] Optimizing DNF configuration..."
if ! grep -q "max_parallel_downloads" /etc/dnf/dnf.conf; then
    cat >> /etc/dnf/dnf.conf << 'EOF'

# GCP optimizations
max_parallel_downloads=10
fastestmirror=True
metadata_expire=7d
EOF
fi

echo "[4/4] Rebuilding DNF cache..."
dnf clean all
dnf makecache

echo "=== Setup complete ==="
echo "Enabled repos:"
dnf repolist --enabled
echo ""
free -h
```

Save as `gcp-rhel-setup.sh` and run:

```bash
chmod +x gcp-rhel-setup.sh
sudo ./gcp-rhel-setup.sh
```

## 5. Verification

After setup, verify the improvements:

```bash
# Check swap is active
free -h

# Check enabled repos (should be fewer)
dnf repolist --enabled

# Test DNF speed (should complete in seconds, not minutes)
time dnf check-update
```

### Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Enabled repos | 17+ | 8-10 |
| Metadata size | ~550 MB | ~250 MB |
| Package count | 123,000+ | ~60,000 |
| `dnf repolist` time | 2-5 min | 30-60 sec |

## Troubleshooting

### SSH Connection Hangs

If you can't SSH into the instance:
1. Use **GCP Serial Console**: Compute Engine → VM instances → Connect to serial console
2. Or **restart the instance** from the GCP Console

### DNF Still Slow

Check what's consuming time:

```bash
# See which repos are being refreshed
dnf -v repolist 2>&1 | head -30

# Check for large metadata downloads
```

### Out of Memory

If OOM still occurs:
1. Increase swap size
2. Upgrade to a larger instance
3. Use `dnf --setopt=install_weak_deps=False` to reduce dependency resolution overhead

---

*Last updated: January 2026*
