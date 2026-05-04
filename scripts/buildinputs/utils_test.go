package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestParseBuildArgFile(t *testing.T) {
	tests := []struct {
		name    string
		content string
		want    map[string]string
		wantErr bool
	}{
		{
			name:    "basic key=value pairs",
			content: "FOO=bar\nBAZ=qux\n",
			want:    map[string]string{"FOO": "bar", "BAZ": "qux"},
		},
		{
			name:    "values with spaces",
			content: "LABEL_SUMMARY=Minimal Jupyter notebook image for ODH notebooks\n",
			want:    map[string]string{"LABEL_SUMMARY": "Minimal Jupyter notebook image for ODH notebooks"},
		},
		{
			name:    "values with equals signs",
			content: "URL=https://example.com?foo=bar&baz=qux\n",
			want:    map[string]string{"URL": "https://example.com?foo=bar&baz=qux"},
		},
		{
			name:    "comments and blank lines skipped",
			content: "# this is a comment\n\nFOO=bar\n# another comment\nBAZ=qux\n\n",
			want:    map[string]string{"FOO": "bar", "BAZ": "qux"},
		},
		{
			name:    "leading whitespace trimmed, value preserved",
			content: "  FOO=bar  \n  # comment  \n  BAZ=qux  \n",
			want:    map[string]string{"FOO": "bar", "BAZ": "qux"},
		},
		{
			name:    "empty value",
			content: "LABEL_COM_REDHAT_COMPONENT=\n",
			want:    map[string]string{"LABEL_COM_REDHAT_COMPONENT": ""},
		},
		{
			name:    "real conf file format",
			content: "INDEX_URL=https://console.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA1/cpu-ubi9-test/simple/\nBASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest\nPYLOCK_FLAVOR=cpu\n",
			want: map[string]string{
				"INDEX_URL":    "https://console.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA1/cpu-ubi9-test/simple/",
				"BASE_IMAGE":   "quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest",
				"PYLOCK_FLAVOR": "cpu",
			},
		},
		{
			name:    "line without equals sign",
			content: "FOO=bar\nINVALID_LINE\n",
			wantErr: true,
		},
		{
			name:    "empty file",
			content: "",
			want:    map[string]string{},
		},
		{
			name:    "only comments and blanks",
			content: "# comment\n\n# another\n",
			want:    map[string]string{},
		},
		{
			name:    "no trailing newline",
			content: "FOO=bar",
			want:    map[string]string{"FOO": "bar"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "test.conf")
			if err := os.WriteFile(path, []byte(tt.content), 0644); err != nil {
				t.Fatal(err)
			}

			got, err := parseBuildArgFile(path)
			if (err != nil) != tt.wantErr {
				t.Fatalf("parseBuildArgFile() error = %v, wantErr %v", err, tt.wantErr)
			}
			if !tt.wantErr {
				if diff := cmp.Diff(tt.want, got); diff != "" {
					t.Errorf("parseBuildArgFile() mismatch (-want +got):\n%s", diff)
				}
			}
		})
	}
}

func TestParseBuildArgFileMissing(t *testing.T) {
	_, err := parseBuildArgFile("/nonexistent/path/to/file.conf")
	if err == nil {
		t.Fatal("expected error for missing file, got nil")
	}
}
