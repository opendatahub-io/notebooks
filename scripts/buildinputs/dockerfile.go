package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"path/filepath"
	"strings"

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
)

func getDockerfileDeps(dockerfile string, targetArch string, buildArgs map[string]string) []string {
	ctx := context.Background()
	data := noErr2(os.ReadFile(dockerfile))

	st, _, _, _, err := dockerfile2llb.Dockerfile2LLB(ctx, data, dockerfile2llb.ConvertOpt{
		// building an image requires fetching the metadata for its parent
		// this fakes a parent so that this tool does not need to do network i/o
		MetaResolver: &testResolver{
			// random digest value
			digest:   "sha256:a1c7d58d98df3f9a67eda799200655b923ebc7a41cad1d9bb52723ae1c81ad17",
			dir:      "/",
			platform: "linux/" + targetArch,
		},
		Config: dockerui.Config{
			BuildArgs:      buildArgs,
			BuildPlatforms: []ocispecs.Platform{{OS: "linux", Architecture: targetArch}},
		},
		Warn: func(rulename, description, url, fmtmsg string, location []parser.Range) {
			log.Printf(rulename, description, url, fmtmsg, location)
		},
	})
	noErr(err)

	definition := noErr2(st.Marshal(ctx))
	return getOpSourceFollowPaths(definition)
}

func getOpSourceFollowPaths(definition *llb.Definition) []string {
	// https://earthly.dev/blog/compiling-containers-dockerfiles-llvm-and-buildkit/
	// https://stackoverflow.com/questions/73067660/what-exactly-is-the-frontend-and-backend-of-docker-buildkit

	opsByDigest := make(map[digest.Digest]llbOp, len(definition.Def))
	for _, dt := range definition.Def {
		var op pb.Op
		if err := op.UnmarshalVT(dt); err != nil {
			panic("failed to parse op")
		}
		dgst := digest.FromBytes(dt)
		ent := llbOp{
			Op:         &op,
			Digest:     dgst,
			OpMetadata: definition.Metadata[dgst].ToPB(),
		}
		opsByDigest[dgst] = ent
	}

	var result []string
	for _, opDef := range opsByDigest {
		switch top := opDef.Op.Op.(type) {
		// https://github.com/moby/buildkit/blob/v0.24/solver/pb/ops.proto#L308-L325
		case *pb.Op_File:
			for _, a := range top.File.Actions {
				// NOTE CAREFULLY: FileActionCopy copies files from secondaryInput on top of input
				if cpy := a.GetCopy(); cpy != nil {
					if inputIsFromLocalContext(a.SecondaryInput, opDef.Op.Inputs, opsByDigest) {
						result = append(result, cleanPath(cpy.Src))
					}
				}
			}
		case *pb.Op_Exec:
			for _, m := range top.Exec.Mounts {
				if inputIsFromLocalContext(m.Input, opDef.Op.Inputs, opsByDigest) {
					result = append(result, cleanPath(m.Selector))
				}
			}
		}
	}

	return result
}

func cleanPath(path string) string {
	return noErr2(filepath.Rel("/", filepath.Clean(path)))
}

func inputIsFromLocalContext(input int64, inputs []*pb.Input, opsByDigest map[digest.Digest]llbOp) bool {
	// input is -1 if the input is a FROM scratch or equivalent
	if input == -1 {
		return false
	}

	srcDigest := digest.Digest(inputs[input].Digest)
	sourceOp := opsByDigest[srcDigest]
	if src, ok := sourceOp.Op.Op.(*pb.Op_Source); ok {
		// local://context is the primary context, but there may be multiple named contexts
		return strings.HasPrefix(src.Source.Identifier, "local://")
	}
	return false
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

	if opt.ImageOpt != nil && opt.ImageOpt.Platform != nil {
		r.platform = platforms.Format(*opt.ImageOpt.Platform)
	}

	dt, err := json.Marshal(img)
	if err != nil {
		return "", "", nil, errors.WithStack(err)
	}
	return ref, r.digest, dt, nil
}
