package main

import (
	"fmt"
	"net"
	"os"
)

func main() {
	addrs, err := net.LookupHost("quay.io")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Go DNS lookup failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Go DNS lookup OK: %v\n", addrs)
}
