// llm-powered reimplementation of github.com/MakeNowJust/heredoc
package main

import (
	"math"
	"strings"
)

// Doc removes common leading whitespace from every line in a string.
func Doc(s string) string {
	lines := strings.Split(s, "\n")
	minIndent := math.MaxInt32

	// First, find the minimum indentation of non-empty lines.
	for _, line := range lines {
		if len(strings.TrimSpace(line)) == 0 {
			continue // Skip empty or whitespace-only lines
		}

		indent := 0
		for _, r := range line {
			if r == ' ' || r == '\t' {
				indent++
			} else {
				break
			}
		}

		if indent < minIndent {
			minIndent = indent
		}
	}

	// If no common indentation is found, return the original string.
	if minIndent == math.MaxInt32 {
		return s
	}

	// Create a builder to efficiently construct the new string.
	var builder strings.Builder
	for i, line := range lines {
		if i == 0 && line == "" {
			continue // Skip the first line if it's empty.
		}
		if len(strings.TrimSpace(line)) == 0 {
			if i != len(lines)-1 {
				// Unless this is the last line, in which case we drop trailing whitespace.
				builder.WriteString(line) // Keep empty lines as they are.
			}
		} else {
			// Trim the minimum common indentation from the start of the line.
			builder.WriteString(line[minIndent:])
		}

		// Add the newline back, except for the very last line.
		if i < len(lines)-1 {
			builder.WriteString("\n")
		}
	}

	return builder.String()
}
