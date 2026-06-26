#! /usr/bin/env python3

import glob
import pathlib
import tempfile

import pyfakefs.fake_filesystem
import pytest
import structlog

from ci.logging_config import configure_logging
from scripts.sandbox import _copy_tree, _ignored_dir_names, _load_dockerignore, setup_sandbox

log = structlog.get_logger()

ROOT_DIR = pathlib.Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _setup_logging():
    configure_logging()


class TestSandbox:
    def test_filesystem_file(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        pathlib.Path("a").write_text("a")

        with tempfile.TemporaryDirectory(delete=True) as tmpdir:
            setup_sandbox([pathlib.Path("a")], pathlib.Path(tmpdir))
            assert (pathlib.Path(tmpdir) / "a").is_file()

    def test_filesystem_dir_with_file(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        pathlib.Path("a/").mkdir()
        pathlib.Path("a/b").write_text("b")

        with tempfile.TemporaryDirectory(delete=True) as tmpdir:
            setup_sandbox([pathlib.Path("a")], pathlib.Path(tmpdir))
            assert (pathlib.Path(tmpdir) / "a").is_dir()
            assert (pathlib.Path(tmpdir) / "a" / "b").is_file()

    def test_filesystem_dir_with_dir_with_file(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        pathlib.Path("a/b").mkdir(parents=True)
        pathlib.Path("a/b/c").write_text("c")

        with tempfile.TemporaryDirectory(delete=True) as tmpdir:
            setup_sandbox([pathlib.Path("a")], pathlib.Path(tmpdir))
            assert (pathlib.Path(tmpdir) / "a").is_dir()
            assert (pathlib.Path(tmpdir) / "a" / "b").is_dir()
            assert (pathlib.Path(tmpdir) / "a" / "b" / "c").is_file()

    def test_filesystem_file_in_dir_in_dir(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        pathlib.Path("a/b").mkdir(parents=True)
        pathlib.Path("a/b/c").write_text("c")

        with tempfile.TemporaryDirectory(delete=True) as tmpdir:
            setup_sandbox([pathlib.Path("a/b/c")], pathlib.Path(tmpdir))
            for g in glob.glob("**/*", recursive=True):
                log.debug(g)
            assert (pathlib.Path(tmpdir) / "a").is_dir()
            assert (pathlib.Path(tmpdir) / "a" / "b").is_dir()
            assert (pathlib.Path(tmpdir) / "a" / "b" / "c").is_file()


@pytest.fixture
def repo_root(fs: pyfakefs.fake_filesystem.FakeFilesystem) -> pathlib.Path:
    root = pathlib.Path("/repo")
    root.mkdir()
    return root


class TestLoadDockerignore:
    def test_returns_empty_when_no_dockerignore(self, repo_root: pathlib.Path):
        assert _load_dockerignore(repo_root) == []

    def test_skips_comments_and_blank_lines(self, repo_root: pathlib.Path):
        (repo_root / ".dockerignore").write_text(
            "# this is a comment\n\n**/node_modules/\n  \n.pnpm-store/\n"
        )
        result = _load_dockerignore(repo_root)
        assert result == ["**/node_modules/", ".pnpm-store/"]

    def test_returns_all_non_comment_lines(self, repo_root: pathlib.Path):
        (repo_root / ".dockerignore").write_text("bin/\nci/\n**/node_modules/\n")
        result = _load_dockerignore(repo_root)
        assert result == ["bin/", "ci/", "**/node_modules/"]


class TestIgnoredDirNames:
    def test_extracts_globstar_patterns(self, repo_root: pathlib.Path):
        (repo_root / ".dockerignore").write_text("**/node_modules/\n**/.pnpm-store/\n")
        root_only, any_depth = _ignored_dir_names(repo_root)
        assert root_only == set()
        assert "node_modules" in any_depth
        assert ".pnpm-store" in any_depth

    def test_splits_root_relative_patterns(self, repo_root: pathlib.Path):
        (repo_root / ".dockerignore").write_text("ci/\nbin/\nnode_modules/\n")
        root_only, any_depth = _ignored_dir_names(repo_root)
        assert root_only == {"ci", "bin", "node_modules"}
        assert any_depth == set()

    def test_excludes_nested_path_patterns(self, repo_root: pathlib.Path):
        (repo_root / ".dockerignore").write_text("**/a/b/\n")
        root_only, any_depth = _ignored_dir_names(repo_root)
        assert root_only == set()
        assert "a/b" not in any_depth
        assert "b" not in any_depth

    def test_excludes_negation_patterns(self, repo_root: pathlib.Path):
        (repo_root / ".dockerignore").write_text("**/vendor/\n!**/vendor/\n")
        root_only, any_depth = _ignored_dir_names(repo_root)
        assert root_only == set()
        assert any_depth == {"vendor"}

    def test_returns_empty_when_no_dockerignore(self, repo_root: pathlib.Path):
        assert _ignored_dir_names(repo_root) == (set(), set())

    def test_real_dockerignore(self):
        root_only, any_depth = _ignored_dir_names(ROOT_DIR)
        assert root_only == {
            "bin", "ci", "tests", ".idea", "env", "venv", ".venv", "docs", "examples",
        }
        assert any_depth == {
            "node_modules", ".mypy_cache", ".pytest_cache", "__pycache__",
        }


class TestCopyTreeWithIgnore:
    def test_ignored_dir_not_copied(self, tmp_path: pathlib.Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "keep").mkdir()
        (src / "keep" / "file.txt").write_text("keep me")
        (src / "node_modules").mkdir()
        (src / "node_modules" / "package.json").write_text("{}")

        dst = tmp_path / "dst"
        dst.mkdir()
        _copy_tree(src, dst, dir_ignore_names={"node_modules"})

        assert (dst / "keep" / "file.txt").is_file()
        assert not (dst / "node_modules").exists()

    def test_dotfile_ignored_dir_not_copied(self, tmp_path: pathlib.Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "good").mkdir()
        (src / "good" / "data").write_text("data")
        (src / ".pnpm-store").mkdir()
        (src / ".pnpm-store" / "v10").mkdir()
        (src / ".pnpm-store" / "v10" / "pkg").write_text("pkg")

        dst = tmp_path / "dst"
        dst.mkdir()
        _copy_tree(src, dst, dir_ignore_names={".pnpm-store"})

        assert (dst / "good" / "data").is_file()
        assert not (dst / ".pnpm-store").exists()

    def test_no_ignore_set_copies_everything(self, tmp_path: pathlib.Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "node_modules" / "pkg").mkdir(parents=True)
        (src / "node_modules" / "pkg" / "index.js").write_text("module.exports = {}")

        dst = tmp_path / "dst"
        dst.mkdir()
        _copy_tree(src, dst)  # no dir_ignore_names

        assert (dst / "node_modules" / "pkg" / "index.js").is_file()

    def test_root_only_ci_not_ignored_in_nested_tree(self, tmp_path: pathlib.Path):
        src = tmp_path / "codeserver/prefetch-input/patches/code-server-v4.106.3"
        (src / "ci/build").mkdir(parents=True)
        (src / "ci/build/build-vscode.sh").write_text("#!/bin/bash")

        dst = tmp_path / "dst"
        dst.mkdir()
        _copy_tree(
            src,
            dst / src.relative_to(tmp_path),
            repo_base_rel=src.relative_to(tmp_path),
            root_only_ignore={"ci"},
            any_depth_ignore=set(),
        )

        assert (dst / src.relative_to(tmp_path) / "ci/build/build-vscode.sh").is_file()

    def test_root_only_ci_ignored_at_repo_root(self, tmp_path: pathlib.Path):
        src = tmp_path / "repo"
        src.mkdir()
        (src / "ci").mkdir()
        (src / "ci/build.sh").write_text("#!/bin/bash")
        (src / "keep").mkdir()

        dst = tmp_path / "dst"
        dst.mkdir()
        _copy_tree(
            src,
            dst / "repo",
            repo_base_rel=pathlib.Path("."),
            root_only_ignore={"ci"},
            any_depth_ignore=set(),
        )

        assert not (dst / "repo/ci").exists()
        assert (dst / "repo/keep").is_dir()
