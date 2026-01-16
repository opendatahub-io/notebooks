package main

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
)

const (
	zig          = "/mnt/zig"
	glibcVersion = "2.34"
)

func getTarget(subcommand string, args []string) string {
	var arch string
	switch os.Getenv("ZIGCC_ARCH") {
	case "amd64":
		arch = "x86_64"
	case "arm64":
		arch = "aarch64"
	case "ppc64le":
		arch = "powerpc64le"
	case "s390x":
		arch = "s390x"
	default:
		fmt.Fprintf(os.Stderr, "zigcc.go: Error: unknown architecture: %s\n", os.Getenv("ZIGCC_ARCH"))
		os.Exit(1)
	}

	// target glibc 2.28 or newer (supports FORTIFY_SOURCE)
	//return arch + "-linux-gnu"
	// specify glibc version with . separator between gnu and the version, otherwise
	//  error: unable to parse target query 'x86_64-linux-gnu2.34': UnknownApplicationBinaryInterface
	//  error: unable to parse target query 'x86_64-linux-gnu+2.34': UnknownApplicationBinaryInterface
	//  error: unable to parse target query 'x86_64-unknown-linux-gnu.2.34': UnknownOperatingSystem
	//  error: unable to parse target query 'x86_64-linux-gnuabi2.34': UnknownApplicationBinaryInterface
	// but for some reason, I'm still having problems with npm
	//  zig c++ -target s390x-linux-gnu.2.34 -o Release/obj.target/windows.node -shared -pthread -rdynamic -m64 -march=z196 -Wl,-soname=windows.node -Wl,--start-group -Wl,--end-group
	//  npm error zig: error: version '.2.34' in target triple 's390x-unknown-linux-gnu.2.34' is invalid
	if subcommand == "c++" {
		// https://github.com/ziglang/zig/issues/25994#issuecomment-3562961055
		return arch + "-linux-gnu"
	}
	if slices.Contains(args, "--version") || slices.Contains(args, "-v") {
		// https://github.com/ziglang/zig/issues/22269
		return arch + "-linux-gnu"
	}
	return arch + "-linux-gnu" + "." + glibcVersion
}

func processArg0(arg0 string) (string, error) {
	switch arg0 {
	case "cc":
		return "cc", nil
	case "c++":
		return "c++", nil

	// `llvm-` prefix so that CMake finds it
	// https://gitlab.kitware.com/cmake/cmake/-/issues/23554
	// https://gitlab.kitware.com/cmake/cmake/-/issues/18712#note_1006035
	// ../../libtool: line 1887: /mnt/ar: No such file or directory
	case "ar", "llvm-ar":
		return "ar", nil
	case "ranlib", "llvm-ranlib":
		return "ranlib", nil
	case "strip", "llvm-strip":
		return "strip", nil

	default:
		return "", fmt.Errorf("zigcc.go: Error: unknown wrapper name: %s", arg0)
	}
}

func processArgs(args []string) []string {
	newArgs := make([]string, 0, len(args))
	for _, arg := range args {
		// deal with -Wp,-D_FORTIFY_SOURCE=2:
		//  this comes in https://github.com/giampaolo/psutil/blob/master/setup.py#L254
		//  build defaults to using python's flags and they are the RHEL fortified ones
		if strings.HasPrefix(arg, "-Wp,") {
			newArgs = append(newArgs, strings.Split(arg, ",")[1:]...)
		} else {
			newArgs = append(newArgs, arg)
		}
	}
	return newArgs
}

func main() {
	arg0 := filepath.Base(os.Args[0])
	subcommand, err := processArg0(arg0)
	if err != nil {
		fmt.Fprintf(os.Stderr, "zigcc.go: Error: %v\n", err)
		os.Exit(1)
	}

	argv := os.Args[1:]
	target := getTarget(subcommand, argv)

	newArgs := []string{
		zig,
		subcommand,
	}
	if subcommand == "cc" || subcommand == "c++" {
		newArgs = append(newArgs, "-target", target)
		// codeserver: :33:10: fatal error: 'X11/Xlib.h' file not found
		// -isystem=... does not work, requires passing as two separate args
		newArgs = append(newArgs,
			"--sysroot", "/",
			"-isystem", "/usr/include",
			"-L/usr/lib64",
			"-isystem", "/usr/local/include",
			"-L/usr/local/lib64")
	}
	newArgs = append(newArgs, processArgs(argv)...)

	env := os.Environ()
	if err := syscall.Exec(newArgs[0], newArgs, env); err != nil {
		fmt.Fprintf(os.Stderr, "zigcc.go: Error executing zig: %v\n", err)
		os.Exit(1)
	}
}
