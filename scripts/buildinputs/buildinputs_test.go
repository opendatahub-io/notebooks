package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func globDockerfiles(dir string) ([]string, error) {
	files := make([]string, 0)
	err := filepath.Walk(dir, func(path string, f os.FileInfo, err error) error {
		if filepath.Base(path) == "Dockerfile" {
			files = append(files, path)
		}
		return nil
	})

	return files, err
}

// TestParseAllDockerfiles checks there are no panics when processing all Dockerfiles we have
func TestParseAllDockerfiles(t *testing.T) {
	projectRoot := "../../"
	dockerfiles := noErr2(globDockerfiles(projectRoot))

	if len(dockerfiles) < 6 {
		t.Fatalf("not enough Dockerfiles found, got %+v", dockerfiles)
	}

	for _, dockerfile := range dockerfiles {
		t.Run(dockerfile, func(t *testing.T) {
			result := getDockerfileDeps(dockerfile)
			if result == "" {
				// no deps in the dockerfile
				return
			}
			data := make([]string, 0)
			noErr(json.Unmarshal([]byte(result), &data))
			for _, path := range data {
				stat := noErr2(os.Stat(filepath.Join(projectRoot, path)))
				if stat.IsDir() {
					// log this very interesting observation
					t.Logf("dockerfile copies in a whole directory: %s", path)
				}
			}
		})
	}
}
