package main

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"slices"
	"strings"
	"testing"
)

func globDockerfiles(dir string) ([]string, error) {
	files := make([]string, 0)
	err := filepath.Walk(dir, func(path string, f os.FileInfo, err error) error {
		if strings.HasPrefix(filepath.Base(path), "Dockerfile.") {
			files = append(files, path)
		}
		return nil
	})

	return files, err
}

// TestParseAllDockerfiles checks there are no panics when processing all Dockerfiles we have
func TestParseAllDockerfiles(t *testing.T) {
	_, currentFilePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("failed to get caller information")
	}

	projectRoot := filepath.Join(filepath.Dir(currentFilePath), "../../")
	dockerfiles := noErr2(globDockerfiles(projectRoot))
	t.Logf("found %d Dockerfiles in %s", len(dockerfiles), projectRoot)

	if len(dockerfiles) < 6 {
		t.Fatalf("not enough Dockerfiles found, got %+v", dockerfiles)
	}

	for _, dockerfile := range dockerfiles {
		t.Run(dockerfile, func(t *testing.T) {
			result := getDockerfileDeps(dockerfile, "amd64")
			if len(result) == 0 {
				// no deps in the dockerfile
				return
			}
			for _, path := range result {
				stat, err := os.Stat(filepath.Join(projectRoot, path))
				if err != nil {
					t.Fatal(err)
				}
				if stat.IsDir() {
					// log this very interesting observation
					t.Logf("dockerfile copies in a whole directory: %s", path)
				}
			}
		})
	}
}

// TestParseDockerfileWithBindMount checks for a bug where a Dockerfile with RUN --mount=type=bind,src=foo,dst=bar would report it has no inputs
func TestParseDockerfileWithBindMount(t *testing.T) {
	dockerfile := filepath.Join(t.TempDir(), "Dockerfile")
	// language=Dockerfile
	noErr(os.WriteFile(dockerfile, []byte(Doc(`
		FROM codeserver AS tests
		ARG CODESERVER_SOURCE_CODE=codeserver/ubi9-python-3.12
		COPY ${CODESERVER_SOURCE_CODE}/test /tmp/test
		RUN --mount=type=tmpfs,target=/opt/app-root/src --mount=type=bind,src=foo,dst=bar <<'EOF'
		set -Eeuxo pipefail
		python3 /tmp/test/test_startup.py |& tee /tmp/test_log.txt
		EOF
	`)), 0644))

	//dockerfile = "/Users/jdanek/IdeaProjects/notebooks/jupyter/rocm/pytorch/ubi9-python-3.12/Dockerfile.rocm"

	result := getDockerfileDeps(dockerfile, "amd64")
	expected := []string{"codeserver/ubi9-python-3.12/test", "foo"}
	if !reflect.DeepEqual(
		slices.Sorted(slices.Values(result)),
		slices.Sorted(slices.Values(expected)),
	) {
		t.Errorf("expected %v but got %v", expected, result)
	}
}

func TestParseFileWithStageCopy(t *testing.T) {
	dockerfile := filepath.Join(t.TempDir(), "Dockerfile")
	// language=Dockerfile
	noErr(os.WriteFile(dockerfile, []byte(Doc(`
		FROM codeserver
		COPY --from=registry.access.redhat.com/ubi9/ubi /etc/yum.repos.d/ubi.repo /etc/yum.repos.d/ubi.repo
	`)), 0644))

	result := getDockerfileDeps(dockerfile, "amd64")
	if len(result) != 0 {
		t.Fatalf("unexpected deps reported for the dockerfile: %s", result)
	}
}

func TestParseFileWithStageMount(t *testing.T) {
	dockerfile := filepath.Join(t.TempDir(), "Dockerfile")
	// language=Dockerfile
	noErr(os.WriteFile(dockerfile, []byte(Doc(`
		FROM javabuilder
		RUN --mount=type=bind,from=build,source=/.m2_repository,target=/.m2_repository \
			mvn package
	`)), 0644))

	result := getDockerfileDeps(dockerfile, "amd64")
	if len(result) != 0 {
		t.Fatalf("unexpected deps reported for the dockerfile: %s", result)
	}
}
