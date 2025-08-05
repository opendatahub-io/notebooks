package main

import (
	"flag"
	"fmt"
	"os"
	"strings"
)

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

	flag.Parse()
	for _, dockerfile := range flag.Args() {
		deps := getDockerfileDeps(dockerfile, targetArch)
		fmt.Println(deps)
	}
}
