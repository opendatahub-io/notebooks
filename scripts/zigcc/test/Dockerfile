FROM quay.io/centos/centos:stream9

# Don't install the GCC compiler, we will inject our own CC
#RUN dnf install -y gcc

# Check CC is in fact injected
RUN /bin/bash <<'EOF'
set -Eeuxo pipefail
ls ${CC}
${CC} --version
EOF

#RUN /mnt/zig clang -x c /dev/null --no-default-config -target s390x-unknown-linux5.10.0-gnu2.34.0 -mhard-float -fno-PIE -fPIC -gdwarf-4 -gdwarf32 -fno-lto -MD -MV -MF /root/.cache/zig/tmp/4ee4407ea328f5c8-null.o.d -fhosted -fno-omit-frame-pointer
#RUN /mnt/zig cc -target s390x-linux-gnu.2.34 --sysroot / -isystem /usr/include -L/usr/lib64 -isystem /usr/local/include -L/usr/local/lib64 -dM -E -x c /dev/null
RUN /mnt/zig -cc1 -triple x86_64-unknown-linux5.10.0-gnu2.34.0 -E -disable-free -clear-ast-before-backend -disable-llvm-verifier -discard-value-names -main-file-name abi-note.S -mrelocation-model pic -pic-level 2 -fhalf-no-semantic-interposition -mframe-pointer=all -fmath-errno -ffp-contract=on -fno-rounding-math

# Create a directory for the program
RUN mkdir /app

# Copy the C source code into the container
RUN sh -c 'cat > /app/hello.c' <<EOF
#include <stdio.h>
int main() {
    printf("Hello, World!\\n");
    return 0;
}
EOF

# Compile the C program
RUN ${CC} /app/hello.c -o /app/hello
# Check it works
RUN /app/hello

# Set the entry point to run the compiled program
CMD ["/app/hello"]
