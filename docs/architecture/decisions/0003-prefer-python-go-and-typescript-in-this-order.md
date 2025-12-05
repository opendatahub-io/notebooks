# 3. Prefer Python, Go, and Typescript (in this order)

Date: 2025-10-31

## Status

Proposed

## Context

We have many Bash scripts; often they are inline scripts embedded in Dockerfiles.
This is hindering code reuse and makes using good software engineering practices difficult.

The current team self-reported that they are comfortable with Python, Go, and (to a lesser degree) TypeScript.
Use these languages in preference to Bash.

## Decision

The team has agreed to use Python, Go, and TypeScript, in this order.

For any new development, we should use the most appropriate language out of these.
Old code should be gradually migrated to one of the preferred languages.

We should avoid using Bash for anything more complicated than a `RUN dnf install -y ... && dnf clean all`.

### Bash

Titus Winters presented about programming languages being [software-engineering-friendly](https://youtu.be/yA_wUiNuhSc&t=649) or unfriendly.
Bash was not mentioned but it should fall into the unfriendly category.
It does not have proper runtime types (everything in Bash is a string, or possibly an array of strings),
it does not even have proper value-returning functions!

There are efforts to level up Bash scripting, such as the `set -Eeuxo pipefail`, but it has
[problems of its own](https://www.reddit.com/r/bash/comments/mivbcm/comment/gt8harr/):

> `errexit`, `nounset` and `pipefail` are imperfect implementations of otherwise sane ideas, and unfortunately they often amount to being unreliable interfaces that are less familiar and less understood than simply living without them. It's perfectly fine to want them to work as advertised, and I think we all would like that, but they don't, so shouldn't be recommended so blindly, nor advertised as a "best practice"—they aren't.

There is also the [bats](https://github.com/bats-core/bats-core) testing framework which does show promise if forced to live with a Bash codebase.

### Python

<span style="color:green;">⊕</span> The semantics of Python are mostly familiar to the team members and they are comfortable using Python.

<span style="color:green;">⊕</span> Pytest as the currently most popular test discovery and execution tool.

<span style="color:red;">⊖</span> Rewriting Bash scripts to Python is verbose. Library to help with this is [sh](https://github.com/amoffat/sh) and others.

<span style="color: red;">⊖</span> The indentation-based syntax is obnoxious, multiline lambdas are not available.

### Go

_90% Perfect, 100% of the time._ [Brad Fitzpatrick, 2014](https://go.dev/talks/2014/gocon-tokyo.slide), [slide #36](https://go.dev/talks/2014/gocon-tokyo.slide#36)

<span style="color:green;">⊕</span> Good performance,
creates native executables,
first-class library support for dealing with Kubernetes.

<span style="color:green;">⊕</span> Often competes with Python in language choice debates,
vastly superior performance to Python and TypeScript both.

<span style="color: red;">⊖</span> Requires compilation step,
type system is not very expressive,
the language does not believe in programming in types (the way some typed functional languages or Rust do).

<span style="color: red;">⊖</span> Has little syntactic sugar, already felt dated the year it came out.

### TypeScript

_The language of the web._

<span style="color:green;">⊕</span> Playwright has best support for TypeScript, other language bindings are a bit of a second class citizen.

<span style="color: gray;">🛈</span> We will consider using full-stack TypeScript in preference to having either a Python or Go backend to a TypeScript frontend.

<span style="color: red;">⊖</span> It's still JavaScript underneath, so there is much inherited weirdness,
such as the `this` keyword being different depending on how a function is called.

## Typechecking

Static analyzability and specifically typechecking is (according to Winters)
an important step to achieving software-engineering friendliness.

The choice in Python is currently between

* Pyrefly
* Pyright (or basedpyright)
* ty

Currently, the project is configured with Pyright, but with type checking disabled.
We should first fix the types with Pyright, gain experience, and then either decide not to use typed Python, or migrate off to one of the other options.

Pyrefly is more complete, whereas ty seems to be more vibrant and dynamic.
Either case, Python type annotations are language standard, so the core does not change,
but the checkers still have lots of implementation-specific behavior left to define themselves.

### Editor support for Python type checkers

VSCode support is pretty much given these days.

In IntelliJ world,
[version 2025.3+ is required for Python tools](https://www.jetbrains.com/help/pycharm/2025.3/lsp-tools.html)
support, as previous versions don't yet have
[LSP support built in](https://plugins.jetbrains.com/docs/intellij/language-server-protocol.html).
There is a
[plugin from Red Hat](https://github.com/redhat-developer/lsp4ij)
that adds LSP client support to IntelliJ, but I did not try to use it.

## Consequences

Less duplication of code due to easier maintenance, and testing of Python code, which should promote reuse.

Simple scripts will be more verbose in Python, but this is a trade-off we can make.

Obvious location to place shared code, sane `import` mechanism.

Allow for [fearless refactoring](https://www.jamesshore.com/v2/blog/2005/merciless-refactoring.html).

> Imagine!
> Do this right, and your code gets cheaper to modify over time!
> That's so amazing, most people don't even think it's possible.

We will need to fight the ever-present tendency to overengineer, and instead we shall promote low-ceremony code.
