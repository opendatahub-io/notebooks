//go:build tools

// This is the old style (pre go 1.24) way of including tool dependencies in Go projects
// See https://go.dev/doc/modules/managing-dependencies#tools for the new way

package tools

import (
	_ "github.com/openshift/check-payload"
)
