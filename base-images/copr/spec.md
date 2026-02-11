# Copr Package Rebuild Tool -- Product Requirements

## Problem Statement

The OpenDataHub Notebooks project builds container base images on CentOS Stream 9 (c9s). These images must provide system-level shared libraries that AIPCC-built Python wheels depend on at runtime. AIPCC wheels are compiled against specific library versions found in the RHEL AI layered repository, but that repository requires a Red Hat subscription and is not accessible during c9s builds.

Today, the base images install system libraries from EPEL 9 and CentOS base repos. For many packages this works, but some AIPCC wheels require newer library versions than what these repos offer. The first concrete case is **h5py**, which needs HDF5 1.14.x (`libhdf5.so.310`), while EPEL 9 only provides HDF5 1.12.1 (`libhdf5.so.200`).

This gap will grow over time as more AIPCC wheels are added that depend on libraries only available in the RHEL AI repo.

## Goal

Provide a tool that rebuilds RPM packages from Fedora source RPMs, targeting Enterprise Linux 9, and publishes them to a publicly accessible Copr repository. The tool must handle the full set of approximately 50 packages from the RHEL AI layered repo, not just individual packages.

## Users

- **Notebook image maintainers** who need to add or update system libraries in the base images.
- **CI/CD pipelines** that build and test the container base images.

## Requirements

### R1: Package Manifest

The tool reads from a declarative YAML manifest file that lists all packages to be rebuilt. Each entry specifies:

- The source package name
- The exact Fedora build version to use (Name-Version-Release)
- An optional human-readable note explaining why the package is needed

The manifest also declares the target Copr project and the Fedora tag to pull SRPMs from.

Adding a new package to the rebuild set requires only adding an entry to this manifest. No other code changes are necessary.

### R2: Automatic Build Ordering

Packages may depend on each other at build time. For example, HDF5 requires libaec, and netcdf requires HDF5. The tool automatically determines the correct build order by:

- Querying what each package provides (binary RPM subpackages and their capabilities)
- Querying what each package requires to build (BuildRequires)
- Computing a valid build order that respects these dependencies, grouping independent packages into parallel waves

The user does not need to manually specify or maintain the build order. Dependencies on packages outside the manifest (e.g. gcc, cmake, zlib-devel) are ignored -- only inter-manifest dependencies affect ordering.

Circular dependencies within the manifest are detected and reported as errors.

### R3: Build Execution

The tool submits packages to the Copr build service in the computed order, building each wave of independent packages in parallel and waiting for all builds in a wave to complete before starting the next wave. It:

- Reports which wave is being built and the submitted build IDs
- Fails immediately when any build in a wave fails, identifying the failed build
- Architecture targeting (x86_64, aarch64) is configured at the Copr project level

### R4: Dry Run

The tool supports a `--dry-run` mode that queries Fedora Koji for package metadata, computes the build plan (waves, package order, SRPM URLs), and displays it without submitting any builds. This allows operators to review the plan before committing to a potentially long rebuild.

The dry-run output shows: the target Copr project, chroot configuration (if any), total package count, total wave count, and for each wave the package NVR and SRPM download URL.

### R5: Manifest Validation

The manifest file is validated on load against a strict schema. Missing required fields, unexpected fields, and type mismatches are caught before any Koji queries or build submissions begin.

### R6: Integration with Base Image Builds

The rebuilt packages are consumable by the existing `aipcc.sh` script during container image builds via standard `dnf install`. The Copr repository is enabled before package installation and disabled afterward, following the same enable/disable pattern used for EPEL.

### R7: Post-Install Verification

After package installation in the container image build, the presence of critical shared libraries is verified. If an expected library (e.g. `libhdf5.so.310`) is missing, the build fails immediately with a clear error message identifying which library was not found.

### R8: Scalability

The tool scales to the full RHEL AI package set (approximately 50 source packages) without requiring per-package manual effort beyond the manifest entry. The dependency resolution, build ordering, and submission are all automatic.

### R9: Verbose Logging

The tool supports a `--verbose` flag that enables detailed debug-level logging of Koji queries, dependency graph construction, and build status polling. Default logging reports progress at the INFO level.

### R10: Build Environment Customization

The target EL9 build environment may differ from Fedora in ways that cause build failures. The manifest declares chroot-level configuration that the tool applies before submitting any builds:

- **Target chroots** (e.g. `epel-9-x86_64`, `epel-9-aarch64`) -- the Copr mock environments to configure.
- **Extra buildroot packages** -- additional packages to install in the mock buildroot alongside the default build group.
- **RPM build options** (`rpmbuild_without`) -- bcond options to disable globally across all builds. For example, `["check"]` skips `%check` sections, which is appropriate when rebuilding known-good Fedora SRPMs whose test suites may exceed Copr's build timeout (e.g. HDF5's MPI parallel tests).

This configuration is applied to each declared chroot before any builds are submitted. The dry-run output includes the chroot configuration that would be applied.

Build tool version mismatches (e.g. EL9 shipping autoconf 2.69 when Fedora SRPMs need >= 2.71) can be resolved by including the required tool as a regular package in the manifest. Copr makes earlier-wave builds available as dependencies for later waves, so a rebuilt autoconf in wave 0 is automatically used by packages in wave 1+.

### R11: Actionable Error Messages

When an operation fails, the tool displays a clear, human-readable error message that includes the underlying cause. In particular:

- If the Copr build service rejects a submission (e.g. project not found, authentication failure, invalid SRPM URL), the error message from the build service is displayed, not a raw stack trace.
- If a build status query fails, the service's error message is shown.
- If manifest loading fails, the validation error is reported immediately.
- All error output is written to stderr with a consistent `Error:` prefix, and the tool exits with a non-zero status code.

## Scope

### In Scope

- Rebuilding Fedora source RPMs for EL9 on Copr
- Automatic dependency resolution and build ordering
- CLI tool for operators to trigger rebuilds
- Manifest-driven package list with schema validation
- Dry-run mode for plan review
- Build environment customization (extra packages in mock chroots)
- Integration with existing `aipcc.sh` installation script
- Post-install verification of critical shared libraries

### Out of Scope

- Rebuilding packages that have RHEL AI-specific patches diverging from Fedora (these need manual review and are tracked separately)
- Hosting a private RPM repository (Copr provides the public repo)
- Automatic detection of when packages need updating (operator-initiated)
- Support for distros other than CentOS Stream 9 / EL9
- Web UI or dashboard for monitoring builds (operators use the Copr web interface directly)

## Constraints

- The tool must not require Red Hat subscriptions or access to internal Red Hat infrastructure
- Source RPMs must come from Fedora Koji, which is publicly accessible
- The Copr build service is community infrastructure with shared capacity; builds may queue
- The tool runs on developer machines (macOS, Linux) and in CI (Linux), using Python 3.14+
- The `copr-cli` command-line tool must be installed and configured with valid Copr API credentials

## Success Criteria

1. The c9s base image build installs HDF5 1.14.x from the Copr repo and `libhdf5.so.310` is present in `/usr/lib64/`
2. AIPCC h5py wheels import successfully in a container built from the c9s base image
3. Adding a new package to the rebuild set requires only a one-line manifest change plus running the tool
4. The dependency resolver correctly orders builds, verified by unit tests covering: linear chains, diamond dependencies, independent package sets, self-dependencies, and cycle detection
5. Invalid manifests are rejected before any external service calls
6. A failed Copr build halts the process immediately with a clear error identifying the failed build
7. All failures produce actionable error messages (with the underlying cause from the build service), not raw stack traces
8. Build environment differences between Fedora and EL9 (e.g. autoconf version) are handled declaratively through the manifest, without per-SRPM patching
9. Packages with long-running test suites (e.g. HDF5 MPI tests) build successfully with `%check` disabled via the manifest's `rpmbuild_without` option
