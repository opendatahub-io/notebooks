package main

import (
	"flag"
	"fmt"
	"os"
	"strings"
)

func main() {
	targetPlatform := os.Getenv("TARGETPLATFORM")
	platformFields := strings.Split(targetPlatform, "/")
	if len(platformFields) != 2 {
		panic(fmt.Sprint(targetPlatform, "format is invalid, should be os/arch"))
	}
	targetOs := platformFields[0]
	targetArch := platformFields[1]

	if targetOs != "linux" {
		panic(fmt.Sprint(targetOs, "not supported"))
	}

	flag.Parse()
	for _, dockerfile := range flag.Args() {
		deps := getDockerfileDeps(dockerfile, targetArch)
		fmt.Println(deps)
	}
}
