package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"slices"
	"strings"
	"testing"
)

// globDockerfiles lists the Dockerfiles tracked by git under dir.
// It uses git ls-files rather than walking the tree so that untracked
// build artifacts (e.g. an in-tree Go module cache or nested worktrees)
// do not contribute third-party Dockerfiles to the parse check.
func globDockerfiles(dir string) ([]string, error) {
	//nolint:gosec // G204: dir is the repo root derived from this test file's own location (runtime.Caller); command and flags are fixed
	out, err := exec.Command("git", "-C", dir, "ls-files", "-z").Output()
	if err != nil {
		return nil, err
	}
	files := make([]string, 0)
	for _, path := range strings.Split(string(out), "\x00") {
		if path == "" {
			continue
		}
		base := filepath.Base(path)
		if base == "Dockerfile.json" {
			continue
		}
		if base == "Dockerfile" || strings.HasPrefix(base, "Dockerfile.") {
			files = append(files, filepath.Join(dir, path))
		}
	}
	return files, nil
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
			buildArgs := map[string]string{"BASE_IMAGE": "fake-image"}

			// Set PYLOCK_FLAVOR from uv.lock.d/ contents if the directory exists
			dockerfileDir := filepath.Dir(dockerfile)
			if entries, err := filepath.Glob(filepath.Join(dockerfileDir, "uv.lock.d", "pylock.*.toml")); err == nil && len(entries) > 0 {
				// Extract flavor from "pylock.cpu.toml" → "cpu"
				base := filepath.Base(entries[0])
				flavor := strings.TrimPrefix(strings.TrimSuffix(base, ".toml"), "pylock.")
				buildArgs["PYLOCK_FLAVOR"] = flavor
			}

			result := getDockerfileDeps(dockerfile, "amd64", buildArgs)
			if len(result) == 0 {
				// no deps in the dockerfile
				return
			}
			for _, path := range result {
				stat, err := os.Stat(filepath.Join(projectRoot, path))
				if err != nil {
					if os.IsNotExist(err) {
						// Some paths reference git submodule content or files that only
						// exist in specific build contexts (e.g. helpers/, prefetch-input/).
						t.Logf("path not found (may require submodule init or build context): %s", path)
						continue
					}
					t.Fatalf("failed to stat %s: %v", path, err)
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

	result := getDockerfileDeps(dockerfile, "amd64", map[string]string{"BASE_IMAGE": "fake-image"})
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

	result := getDockerfileDeps(dockerfile, "amd64", map[string]string{"BASE_IMAGE": "fake-image"})
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

	result := getDockerfileDeps(dockerfile, "amd64", map[string]string{"BASE_IMAGE": "fake-image"})
	if len(result) != 0 {
		t.Fatalf("unexpected deps reported for the dockerfile: %s", result)
	}
}
