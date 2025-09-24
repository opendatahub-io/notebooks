package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

func processArg0(arg0 string) (string, error) {
	switch arg0 {
	case "zig-cc":
		return "cc", nil
	case "zig-c++":
		return "c++", nil
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

	newArgs := make([]string, 0, len(os.Args)+4)
	newArgs = append(newArgs,
		"/mnt/zig", // Path to the real Zig executable.
		subcommand,
		"-target",
		"s390x-linux-gnu.2.34",
	)
	newArgs = append(newArgs, processArgs(os.Args[1:])...)

	env := os.Environ()
	if err := syscall.Exec(newArgs[0], newArgs, env); err != nil {
		fmt.Fprintf(os.Stderr, "Error executing zig: %v\n", err)
		os.Exit(1)
	}
}
