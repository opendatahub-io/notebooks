# 3. Prefer Python, Go, and Typescript (in this order)

Date: 2025-10-31

## Status

Accepted

## Context

We have many Bash scripts, often they are inline scripts embedded in Dockerfiles.
This is hindering code reuse, and makes using good software engineering practices difficult.

The current team self-reported that they are comfortable with Python, Go, and (to a lesser degree) TypeScript.
Use these languages in preference to Bash.

## Decision

The team has agreed to use Python, Go, and Typescript, in this order.

For any new development, we should use the most appropriate language out of these.
Old code should be gradually migrated to one of the preferred languages.

Avoid using Bash for anything more complicated than a `RUN dnf install -y ... && dnf clean all`.

### Python

_The language of AI._

Pytest as the currently most popular test discovery and execution tool.

Rewriting Bash scripts to Python is verbose. Library to help with this is [sh](https://github.com/amoffat/sh) and others.

The indentation-based syntax is obnoxious, multiline lambdas are not available.

### Go

_90% Perfect, 100% of the time._ [Brad Fitzpatrick, 2014](https://go.dev/talks/2014/gocon-tokyo.slide), [slide #36](https://go.dev/talks/2014/gocon-tokyo.slide#36)

Good performance, creates native executables, first class library support for dealing with Kubernetes.

### TypeScript

_The language of the web._

Playwright has best support for TypeScript, other language bindings are a bit of a second class citizen.

We will consider using full-stack TypeScript in preference to having either a Python or Go backend to a TypeScript frontend.

## Consequences

Less duplication of code due to easier maintenance, and testing of Python code, which should promote reuse.

Simple scripts will be more verbose in Python, but this is a trade-off we can make.
