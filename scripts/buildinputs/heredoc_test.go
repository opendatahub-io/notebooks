package main

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestDoc(t *testing.T) {
	input := `
		a
		b
	`
	diff(t, "a\nb\n", Doc(input))
}

// diff errors with a diff between expected and actual if they are not equal.
func diff(t *testing.T, expected, actual string) {
	t.Helper()
	if diff := cmp.Diff(expected, actual); diff != "" {
		t.Errorf("mismatch (-want +got):\n%s", diff)
	}
}
