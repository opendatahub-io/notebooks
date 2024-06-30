package main

import (
	"bufio"
	"fmt"
	"github.com/moby/patternmatcher"
	"log"
	"os"
	"regexp"
)

// main takes path to .dockerignore as a command line argument and reads filenames from stdin
func main() {
	if len(os.Args) != 2 {
		log.Fatalf("Provide one argument: path to .dockerignore")
	}
	file := os.Args[1]

	data, err := os.ReadFile(file)
	if err != nil {
		log.Fatalf("Cannot read file '%s': %s\n", file, err)
	}

	lines := regexp.MustCompile("\r?\n").Split(string(data), -1)
	matcher, err := patternmatcher.New(lines)
	if err != nil {
		log.Fatalf("Failed to parse file '%s': %s", file, err)
	}

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		line := scanner.Text()
		matches, err := matcher.MatchesOrParentMatches(line)
		if err != nil {
			log.Fatalf("Failed to match '%s' against the .dockerignore: %s", line, err)
		}
		if !matches {
			fmt.Println(line)
		}
	}
}
