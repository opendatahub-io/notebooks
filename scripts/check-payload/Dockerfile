# syntax=docker/dockerfile:1.25

FROM --platform=$BUILDPLATFORM registry.access.redhat.com/ubi9/go-toolset:1.26.5-1784751462 AS build

ARG CHECK_PAYLOAD_VERSION

WORKDIR /src
RUN git clone --branch "${CHECK_PAYLOAD_VERSION}" --depth 1 \
    https://github.com/openshift/check-payload.git .

RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

ARG TARGETOS
ARG TARGETARCH
RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -buildvcs=false -ldflags="-s -w" -o /tmp/check-payload .

# check-payload shells out to `rpm -qf` to match files to packages;
# RPM-scoped suppressions ([[rpm.*.ignore]]) fail without it
FROM registry.access.redhat.com/ubi9-minimal:latest

COPY --from=build --chmod=0755 /tmp/check-payload /usr/local/bin/check-payload
USER 65532:0
ENTRYPOINT ["check-payload"]
