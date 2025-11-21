package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

const (
	zig = "/mnt/zig"
)

func getTarget() string {
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
	return arch + "-linux-gnu.2.34"
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

	target := getTarget()

	newArgs := []string{
		zig,
		subcommand,
	}
	if subcommand == "cc" || subcommand == "c++" {
		newArgs = append(newArgs, "-target", target)
	}
	newArgs = append(newArgs, processArgs(os.Args[1:])...)

	env := os.Environ()
	if err := syscall.Exec(newArgs[0], newArgs, env); err != nil {
		fmt.Fprintf(os.Stderr, "zigcc.go: Error executing zig: %v\n", err)
		os.Exit(1)
	}
}
