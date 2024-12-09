package main

import (
	"flag"
	"fmt"
)

func main() {
	flag.Parse()
	for _, dockerfile := range flag.Args() {
		deps := getDockerfileDeps(dockerfile)
		fmt.Println(deps)
	}
}
