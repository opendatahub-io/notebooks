# zigcc

_Launcher for `zig cc`, `zig c++`, and related subcommands for more efficient cross-compilation_

This script helps by using a native compiler binary to compile for the target architecture.
This means that the compiler then is running at the native speed.

## Background

Cross-compilation means compiling for a different architecture than the one on which the compiler is running.
Specifically, it is when you're creating a workbench container image for say x86_64 on an arm64 machine such as an M-series MacBook.
Everything that's running in the container will run slower, because it has to run under qemu.

This slowdown is especially noticeable when compiling C/C++ code for IBM Power and Z, such as Python extension modules that don't have precompiled binaries for these architectures on PyPI.

## Usage

```commandline
gmake codeserver-ubi9-python-3.12 BUILD_ARCH=linux/s390x CONTAINER_BUILD_CACHE_ARGS=
```

This is about 50% faster than cross-compiling through `qemu-s390x-static` or `qemu-ppc64le-static`.

## Cross-compilation overview

### Qemu-user-static

Docker/Podman can perform cross-compilation using `qemu-user-static`.
The idea is to install the various `qemu-user` binaries as interpreters for foreign architecture binaries.
Launching such binary will then automatically run it under qemu interpreter.

Docker is uniquely suitable to run binaries like this, because container images bring all dependencies with them.

### Traditional cross-compilation

For CMake, I can imagine an approach which involves installing a cross compiler and mounting arm64 docker image to provide arm64 environment with libraries.
<https://cmake.org/cmake/help/book/mastering-cmake/chapter/Cross%20Compiling%20With%20CMake.html>

### Zig

https://zig.guide/working-with-c/zig-cc/

The `zig cc` command bundles clang in a way that simplifies its usage for cross compilation,
<https://zig.news/kristoff/cross-compile-a-c-c-project-with-zig-3599>

#### Wrapper (zigcc.go)

We need a wrapper so that we can transform CLI arguments to work with `zig cc`.

The main problem is the `-Wl,D_FORTIFY_SOURCE=2` flag, because zig has limited handling for -Wl, and does not do -Wl,D correctly.

The wrapper should be written in a low-overhead language, like Go, or possibly Bash, certainly not Python.
The lower the overhead of the wrapper, the better, since the compiler is invoked many times during a typical build.

### Debugging

To observe the effect of the wrapper, we can use `execsnoop` from `bcc-tools` to monitor the compiler invocations during a container build.

```commandline
$ podman machine ssh
# bootc usr-overlay
# dnf install bcc-tools
# /usr/share/bcc/tools/execsnoop
```

## Credits

This is inspired by <https://github.com/skupperproject/skupper-router/pull/1100>
