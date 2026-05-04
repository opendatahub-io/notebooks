package main

import (
	"fmt"
	"os"
	"strings"
)

func parseBuildArgFile(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	result := make(map[string]string)
	for line := range strings.SplitSeq(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || line[0] == '#' {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return nil, fmt.Errorf("invalid build-arg line (no '='): %q", line)
		}
		result[key] = value
	}
	return result, nil
}

// noErr panics if the argument (usually a result of a function call)
// returns a != nil error
func noErr(err error) {
	if err != nil {
		panic(err)
	}
}

// noErr2 is a 2-arity variant of noErr, that passes through the first
// value from the argument
func noErr2[T any](result T, err error) T {
	noErr(err)
	return result
}
