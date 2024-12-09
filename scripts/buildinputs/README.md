# buildinputs

Tool to determine what files are required to build a given Dockerfile.

## Design

There are multiple possible solutions to this problem.

### Convert to LLB and analyze the LLB (chosen approach)

At present, the tool works by converting the Dockerfile into LLB (BuildKit's protobuf-based representation) and then
analysing that to get the referenced files.

### Parse the Dockerfile and resolve the AST

Docker provides Go functions to parse a Dockerfile to AST.
It does not provide public functions for the AST resolution, however.

The procedure can be copied either from the LLB convertor code or from regular build code.

It requires handling the following instructions (at minimum):

* `ARG`, `ENV` (file paths will require arg substitution)
* `ADD`, `COPY` (the two main ways to pull files into the build)
* `RUN` (has a `--mount=bind` flag)
* `ONBUILD` in a parent image (that would be probably fine to ignore, as it's not OCI)

### Parse (lex) the Dockerfile ourselves

This is also doable, and it would avoid having to use Go.

The main limitation is that if the implementation we have is incomplete,
then using a new Dockerfile feature (HEREDOC, ...) would require first implementing it in our parser,
which limits further progress.

Another difficulty is that we would surely have bugs and that would decrease the team's confidence in the CI system.
