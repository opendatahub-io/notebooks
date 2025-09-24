package main

import (
	"fmt"
	"reflect"
	"testing"
)

func TestProcessWp(t *testing.T) {
	args := []string{"-Wp,-D_FORTIFY_SOURCE=2"}
	newArgs := processArgs(args)
	if !reflect.DeepEqual(newArgs, []string{"-D_FORTIFY_SOURCE=2"}) {
		t.Fatalf("expected -DFOO=bar, got %v", newArgs)
	}
	for _, tc := range []struct {
		args     []string
		expected []string
	}{
		{
			args:     []string{"-Wp,-D_FORTIFY_SOURCE=2"},
			expected: []string{"-D_FORTIFY_SOURCE=2"},
		},
		{
			args:     []string{"-Wp,-DNDEBUG,-D_FORTIFY_SOURCE=2"},
			expected: []string{"-DNDEBUG", "-D_FORTIFY_SOURCE=2"},
		},
	} {
		t.Run(fmt.Sprint(tc.args), func(t *testing.T) {
			newArgs := processArgs(tc.args)
			if !reflect.DeepEqual(newArgs, tc.expected) {
				t.Fatalf("expected %#v, got %#v", tc.expected, newArgs)
			}
		})
	}
}
