# zigcc

_Launcher for `zig cc`, `zig c++`, and related subcommands for more efficient cross-compilation_

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

The `zig cc` command bundles clang in a way that simplifies its usage for cross compilation,
<https://zig.news/kristoff/cross-compile-a-c-c-project-with-zig-3599>

## Credits

This is inspired by <https://github.com/skupperproject/skupper-router/pull/1100>
