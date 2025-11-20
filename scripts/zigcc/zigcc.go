package main

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
)

const (
	zig = "/mnt/zig"
)

func getTarget() string {
	var arch string
	switch runtime.GOARCH {
	case "amd64":
		arch = "x86_64"
	case "arm64":
		arch = "aarch64"
	case "ppc64le":
		arch = "ppc64le"
	case "s390x":
		arch = "s390x"
	default:
		fmt.Fprintf(os.Stderr, "Error: unknown architecture: %s\n", runtime.GOARCH)
		os.Exit(1)
	}
	return arch + "-linux-gnu.2.34"
}

func processArg0(arg0 string) (string, error) {
	switch arg0 {
	case "cc":
		return "cc", nil
	case "c++":
		return "c++", nil

	// `llvm-` prefix so that CMake finds it
	case "llvm-ar":
		return "ar", nil
	case "llvm-ranlib":
		return "ranlib", nil

	default:
		return "", fmt.Errorf("unknown wrapper name: %s", arg0)
	}
}

func processArgs(args []string) []string {
	newArgs := make([]string, 0, len(args))
	for _, arg := range args {
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
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
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
		fmt.Fprintf(os.Stderr, "Error executing zig: %v\n", err)
		os.Exit(1)
	}
}
