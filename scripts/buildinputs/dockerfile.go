package main

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/containerd/platforms"
	"github.com/moby/buildkit/client/llb"
	"github.com/moby/buildkit/client/llb/sourceresolver"
	"github.com/moby/buildkit/frontend/dockerfile/dockerfile2llb"
	"github.com/moby/buildkit/frontend/dockerfile/parser"
	"github.com/moby/buildkit/frontend/dockerui"
	"github.com/moby/buildkit/solver/pb"
	"github.com/opencontainers/go-digest"
	ocispecs "github.com/opencontainers/image-spec/specs-go/v1"
	"github.com/pkg/errors"
	"log"
	"os"
	"strings"
)

func getDockerfileDeps(dockerfile string) string {
	ctx := context.Background()
	data := noErr2(os.ReadFile(dockerfile))

	st, _, _, _, err := dockerfile2llb.Dockerfile2LLB(ctx, data, dockerfile2llb.ConvertOpt{
		// building an image requires fetching the metadata for its parent
		// this fakes a parent so that this tool does not need to do network i/o
		MetaResolver: &testResolver{
			// random digest value
			digest:   "sha256:a1c7d58d98df3f9a67eda799200655b923ebc7a41cad1d9bb52723ae1c81ad17",
			dir:      "/",
			platform: "linux/amd64",
		},
		Config: dockerui.Config{
			BuildArgs:      map[string]string{"BASE_IMAGE": "fake-image"},
			BuildPlatforms: []ocispecs.Platform{{OS: "linux", Architecture: "amd64"}},
		},
		Warn: func(rulename, description, url, fmtmsg string, location []parser.Range) {
			log.Printf(rulename, description, url, fmtmsg, location)
		},
	})
	noErr(err)

	definition := noErr2(st.Marshal(ctx))
	return getOpSourceFollowPaths(definition)
}

func getOpSourceFollowPaths(definition *llb.Definition) string {
	// https://earthly.dev/blog/compiling-containers-dockerfiles-llvm-and-buildkit/
	// https://stackoverflow.com/questions/73067660/what-exactly-is-the-frontend-and-backend-of-docker-buildkit

	ops := make([]llbOp, 0)
	for _, dt := range definition.Def {
		var op pb.Op
		if err := op.UnmarshalVT(dt); err != nil {
			panic("failed to parse op")
		}
		dgst := digest.FromBytes(dt)
		ent := llbOp{Op: &op, Digest: dgst, OpMetadata: definition.Metadata[dgst].ToPB()}
		ops = append(ops, ent)
	}

	for _, op := range ops {
		switch op := op.Op.Op.(type) {
		case *pb.Op_Source:
			if strings.HasPrefix(op.Source.Identifier, "docker-image://") {
				// no-op
			} else if strings.HasPrefix(op.Source.Identifier, "local://") {
				paths := op.Source.Attrs[pb.AttrFollowPaths]
				return paths
			} else {
				panic(fmt.Errorf("unexpected prefix %v", op.Source.Identifier))
			}
		}
	}
	return ""
}

// llbOp holds data for a single loaded LLB op
type llbOp struct {
	Op         *pb.Op
	Digest     digest.Digest
	OpMetadata *pb.OpMetadata
}

// testResolver provides a fake parent image manifest for the build
type testResolver struct {
	digest   digest.Digest
	dir      string
	platform string
}

func (r *testResolver) ResolveImageConfig(ctx context.Context, ref string, opt sourceresolver.Opt) (string, digest.Digest, []byte, error) {
	var img struct {
		Config struct {
			Env        []string `json:"Env,omitempty"`
			WorkingDir string   `json:"WorkingDir,omitempty"`
			User       string   `json:"User,omitempty"`
		} `json:"config,omitempty"`
	}

	img.Config.WorkingDir = r.dir

	if opt.Platform != nil {
		r.platform = platforms.Format(*opt.Platform)
	}

	dt, err := json.Marshal(img)
	if err != nil {
		return "", "", nil, errors.WithStack(err)
	}
	return ref, r.digest, dt, nil
}
