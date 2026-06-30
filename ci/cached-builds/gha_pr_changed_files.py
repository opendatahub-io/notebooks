import fnmatch
import functools
import logging
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from typing import Literal, cast

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.buildinputs_runner import Platform, buildinputs  # noqa: E402

MAKE = shutil.which("gmake") or shutil.which("make") or "make"


def get_github_token() -> str:
    github_token = os.environ["GITHUB_TOKEN"]
    return github_token


@functools.cache
def _symlink_reverse_map() -> dict[str, list[str]]:
    """Build a map from resolved real path to symlink logical paths.

    Git reports changes to real files only, not to symlinks pointing at them.
    This map lets us expand a list of changed real paths to include the logical
    symlink paths that are affected. Built once per process and cached.
    """
    result: dict[str, list[str]] = {}
    for symlink in PROJECT_ROOT.rglob("*"):
        if not symlink.is_symlink():
            continue
        try:
            logical = str(symlink.relative_to(PROJECT_ROOT))
            resolved = str(symlink.resolve().relative_to(PROJECT_ROOT))
        except (ValueError, OSError, RuntimeError):  # fmt: skip  # parens needed for Python <3.14 (GHA runners)
            # RuntimeError: symlink loops (a→b→a) cause infinite resolution
            continue
        # symlink resolving to itself is not useful
        if logical != resolved:
            result.setdefault(resolved, []).append(logical)
    if result:
        logging.debug(f"Symlink reverse map: {len(result)} targets with symlinks")
    return result


def _resolve_symlinks(paths: list[str]) -> list[str]:
    """Expand paths to include symlinks whose resolved targets match.

    Git reports changes to real files only, not to symlinks pointing at them.
    This adds logical symlink paths when their resolved targets appear in the
    input list.
    """
    if not paths:
        return paths

    reverse = _symlink_reverse_map()
    if not reverse:
        return paths

    original = set(paths)
    expanded = set(original)
    for path in paths:
        for resolved, symlinks in reverse.items():
            if path == resolved:
                expanded.update(symlinks)
            elif path.startswith(resolved + "/"):
                suffix = path[len(resolved) :]
                expanded.update(f"{symlink}{suffix}" for symlink in symlinks)
            elif resolved.startswith(path + "/"):
                expanded.update(symlinks)

    if added := expanded - original:
        logging.info(f"Symlink resolution added {len(added)} paths: {sorted(added)}")
    return sorted(expanded)


def list_changed_files(from_ref: str, to_ref: str) -> list[str]:
    logging.debug("Getting list of changed files from git diff")

    # Use three-dot diff to show changes from merge-base to to_ref
    # This correctly shows only changes introduced by the PR, regardless of how much from_ref has advanced
    # See: https://github.com/opendatahub-io/notebooks/issues/2875
    # https://github.com/red-hat-data-services/notebooks/pull/361: add -- in case to_ref matches a file name in the repo
    files = subprocess.check_output(
        ["git", "diff", "--name-only", f"{from_ref}...{to_ref}", "--"], encoding="utf-8"
    ).splitlines()
    files = _resolve_symlinks(files)

    logging.debug(f"Determined {len(files)} changed files: {files[:100]} (..., printing up to 100 files)")
    return files


def _query_build(make_target: str, query: str, env: dict[str, str] | None = None) -> str:
    results = []

    if env is None:
        env = {}

    envs = []
    for k, v in env.items():
        envs.extend(("-e", f"{k}={v}"))

    pattern = re.compile(r"#\*# " + query + r": <(?P<result>[^>]+)> #\(MACHINE-PARSED LINE\)#\*#\.\.\.")
    try:
        logging.debug(f"Running make in --just-print mode for target {make_target}")
        for line in subprocess.check_output(
            [MAKE, make_target, "--just-print", *envs], encoding="utf-8", cwd=PROJECT_ROOT
        ).splitlines():
            if m := pattern.match(line):
                results.append(m["result"])
    except subprocess.CalledProcessError as e:
        print(f"make --just-print for target {make_target!r} failed: {e.stderr}\n{e.stdout}")
        raise

    if len(results) != 1:
        raise Exception(f"Expected a single query result for target '{make_target}': {results}")

    logging.debug(f"Target {make_target} builds from {results[0]}")
    return results[0]


def get_build_directory(make_target, env: dict[str, str] | None = None) -> str:
    return _query_build(make_target, "Image build directory", env=env)


def get_build_dockerfile(make_target: str, env: dict[str, str] | None = None) -> str:
    return _query_build(make_target, "Image build Dockerfile", env=env)


def find_dockerfiles(directory: str) -> list:
    """Finds and returns a list of files matching the pattern 'Dockerfile*' in the specified directory."""
    matching_files = []
    for filename in os.listdir(directory):
        if fnmatch.fnmatch(filename, "Dockerfile*") and filename != "Dockerfile.konflux":
            matching_files.append(filename)
    return matching_files


def _is_file_in_directory(changed_file: str, directory: str) -> bool:
    """Returns True if changed_file is exactly the directory or is within it."""
    return changed_file == directory or changed_file.startswith(directory + "/")


def should_build_target(changed_files: list[str], target_directory: str) -> str:
    """Returns truthy if there is at least one changed file necessitating a build.
    Falsy (empty) string is returned otherwise."""

    # detect change in the Dockerfile directory
    for changed_file in changed_files:
        if _is_file_in_directory(changed_file, target_directory):
            return changed_file
    # detect change in any of the files outside
    dockerfiles = find_dockerfiles(target_directory)
    for dockerfile in dockerfiles:
        dependencies = _resolve_symlinks(
            [
                str(path)
                for path in buildinputs(
                    target_directory + "/" + dockerfile,
                    platform=cast("Platform", f"linux/{get_go_arch()}"),
                    build_args={"BASE_IMAGE": "fake-image"},
                )
            ]
        )
        logging.debug(f"{target_directory=} {dockerfile=} {dependencies=}")
        if not dependencies:
            continue
        for dependency in dependencies:
            for changed_file in changed_files:
                if _is_file_in_directory(changed_file, dependency):
                    return changed_file
    return ""


def filter_out_unchanged(targets: list[str], changed_files: list[str]) -> list[str]:
    changed = []
    for target in targets:
        python_version = (
            "3.11" if "-python-3.11" in target else "3.12" if "-python-3.12" in target else "invalid-python-version"
        )
        build_directory = get_build_directory(target, env={"RELEASE_PYTHON_VERSION": python_version})
        if reason := should_build_target(changed_files, build_directory):
            logging.info(f"✅ Will build {target} because file {reason} has been changed")
            changed.append(target)
        else:
            logging.info(f"❌ Won't build {target}")
    return changed


def get_go_arch() -> Literal["amd64", "arm64", "ppc64le", "s390x"]:
    if goarch := os.environ.get("GOARCH"):
        match goarch.lower():
            case "amd64" | "arm64" | "ppc64le" | "s390x" as arch:
                return arch
            case _:
                raise ValueError(f"Unsupported GOARCH value: {goarch!r}")
    match platform.machine().lower():
        case "x86_64" | "amd64":
            arch = "amd64"
        case "aarch64" | "arm64":
            arch = "arm64"
        case "ppc64le":
            arch = "ppc64le"
        case "s390x":
            arch = "s390x"
        case _:
            raise Exception(f"Unknown machine architecture: {platform.machine()}")
    return arch


class TestSelf(unittest.TestCase):
    def test_list_changed_files(self):
        """This is PR #556 in opendatahub-io/notebooks"""
        changed_files = list_changed_files(from_ref="4d4841f", to_ref="2c36c11")
        assert set(changed_files) == {
            "codeserver/ubi9-python-3.9/Dockerfile",
            "codeserver/ubi9-python-3.9/run-code-server.sh",
        }

    def test_get_build_directory(self):
        directory = get_build_directory("rocm-jupyter-pytorch-ubi9-python-3.12")
        assert directory == "jupyter/rocm/pytorch/ubi9-python-3.12"

    def test_get_build_dockerfile(self):
        dockerfile = get_build_dockerfile("rocm-jupyter-pytorch-ubi9-python-3.12")
        assert dockerfile == "jupyter/rocm/pytorch/ubi9-python-3.12/Dockerfile.konflux.rocm"

    def test_should_build_target(self):
        current_module = sys.modules[__name__]
        with unittest.mock.patch.object(current_module, "buildinputs", return_value=[]):
            assert "" == should_build_target(["README.md"], "jupyter/datascience/ubi9-python-3.12")

    def test_should_build_target_dependency_change(self):
        fake_return = [pathlib.Path("jupyter/datascience/ubi9-python-3.12/helper.txt")]
        current_module = sys.modules[__name__]
        with unittest.mock.patch.object(current_module, "buildinputs", return_value=fake_return):
            assert (
                should_build_target(
                    ["jupyter/datascience/ubi9-python-3.12/helper.txt"],
                    "jupyter/datascience/ubi9-python-3.12",
                )
                == "jupyter/datascience/ubi9-python-3.12/helper.txt"
            )

    def test_resolve_symlinks_no_symlinks(self):
        """No symlinks in input paths -> returned unchanged."""
        assert _resolve_symlinks(["README.md"]) == ["README.md"]

    def test_resolve_symlinks_empty(self):
        assert _resolve_symlinks([]) == []

    def test_resolve_symlinks_expands_target(self):
        """Editing a symlink target adds the symlink path."""
        result = _resolve_symlinks(["jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu"])
        assert "jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu" in result
        assert "jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu" in result

    def test_resolve_symlinks_pointer_change(self):
        """Editing the symlink itself needs no expansion — already in list."""
        result = _resolve_symlinks(["jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu"])
        assert result == ["jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu"]

    def test_should_build_with_symlinked_dockerfile_target_change(self):
        """Changing Dockerfile.konflux.cpu triggers build for target using Dockerfile.cpu."""
        changed = _resolve_symlinks(["jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu"])
        result = should_build_target(changed, "jupyter/minimal/ubi9-python-3.12")
        assert result

    def test_resolve_symlinks_preserves_suffix_for_directory_symlink(self):
        """When real_dir/sub/file changes and link_dir → real_dir, we should
        get link_dir/sub/file in the expanded list, not just link_dir."""
        _symlink_reverse_map.cache_clear()
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            real_dir = tmpdir / "real_dir"
            real_dir.mkdir()
            (real_dir / "sub").mkdir()
            (real_dir / "sub" / "file.txt").write_text("content")
            link_dir = tmpdir / "link_dir"
            link_dir.symlink_to("real_dir")

            rel_real = str((real_dir / "sub" / "file.txt").relative_to(PROJECT_ROOT))
            rel_link_expected = str((link_dir / "sub" / "file.txt").relative_to(PROJECT_ROOT))

            result = _resolve_symlinks([rel_real])
            assert rel_link_expected in result, f"Expected {rel_link_expected} in result, got {result}"
        _symlink_reverse_map.cache_clear()

    def test_symlink_loop_does_not_crash(self):
        """A symlink loop should be skipped, not crash the scan."""
        _symlink_reverse_map.cache_clear()
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            link_a = tmpdir / "a"
            link_b = tmpdir / "b"
            link_a.symlink_to("b")
            link_b.symlink_to("a")

            result = _resolve_symlinks(["README.md"])
            assert "README.md" in result
        _symlink_reverse_map.cache_clear()
