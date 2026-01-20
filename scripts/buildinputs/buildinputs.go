package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
)

// Define a custom type that matches the flag.Value interface
type repeatFlag []string

func (f *repeatFlag) String() string {
	return strings.Join(*f, ", ")
}

func (f *repeatFlag) Set(value string) error {
	*f = append(*f, value)
	return nil
}

func main() {
	targetPlatform := os.Getenv("TARGETPLATFORM")
	if targetPlatform == "" {
		panic("TARGETPLATFORM environment variable is required")
	}
	platformFields := strings.Split(targetPlatform, "/")
	if len(platformFields) != 2 {
		panic(fmt.Sprintf("TARGETPLATFORM format is invalid: %q, should be os/arch", targetPlatform))
	}
	targetOs := platformFields[0]
	targetArch := platformFields[1]

	if targetOs != "linux" {
		panic(fmt.Sprintf("%s not supported", targetOs))
	}

	var buildArgs repeatFlag
	flag.Var(&buildArgs, "build-arg", "Build argument in the form of key=value, can be specified multiple times.")
	flag.Parse()

	buildArgsMap := make(map[string]string)
	for _, arg := range buildArgs {
		kv := strings.SplitN(arg, "=", 2)
		if len(kv) != 2 {
			panic(fmt.Sprintf("Invalid build argument: %q", arg))
		}
		buildArgsMap[kv[0]] = kv[1]
	}
	if _, ok := buildArgsMap["BASE_IMAGE"]; !ok {
		panic("BASE_IMAGE build argument is required")
	}

	for _, dockerfile := range flag.Args() {
		deps := getDockerfileDeps(dockerfile, targetArch, buildArgsMap)
		// nil slice encodes to null, which is not what we want
		if deps == nil {
			deps = []string{}
		}
		encoder := json.NewEncoder(os.Stdout)
		noErr(encoder.Encode(deps))
	}
}
