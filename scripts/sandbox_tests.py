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


class TestLoadDockerignore:
    def test_returns_empty_when_no_dockerignore(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        root = pathlib.Path("/repo")
        root.mkdir()
        assert _load_dockerignore(root) == []

    def test_skips_comments_and_blank_lines(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        root = pathlib.Path("/repo")
        root.mkdir()
        (root / ".dockerignore").write_text(
            "# this is a comment\n\n**/node_modules/\n  \n.pnpm-store/\n"
        )
        result = _load_dockerignore(root)
        assert result == ["**/node_modules/", ".pnpm-store/"]

    def test_returns_all_non_comment_lines(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        root = pathlib.Path("/repo")
        root.mkdir()
        (root / ".dockerignore").write_text("bin/\nci/\n**/node_modules/\n")
        result = _load_dockerignore(root)
        assert result == ["bin/", "ci/", "**/node_modules/"]


class TestIgnoredDirNames:
    def test_extracts_globstar_patterns(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        root = pathlib.Path("/repo")
        root.mkdir()
        (root / ".dockerignore").write_text("**/node_modules/\n**/.pnpm-store/\n")
        result = _ignored_dir_names(root)
        assert "node_modules" in result
        assert ".pnpm-store" in result

    def test_excludes_root_relative_patterns(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        # Patterns without "**/" prefix only apply at the root of the build
        # context, not recursively inside nested directories.
        root = pathlib.Path("/repo")
        root.mkdir()
        (root / ".dockerignore").write_text("ci/\nbin/\nnode_modules/\n")
        result = _ignored_dir_names(root)
        assert "ci" not in result
        assert "bin" not in result
        assert "node_modules" not in result

    def test_excludes_nested_path_patterns(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        # Patterns with intermediate "/" should not be used as bare dir names.
        root = pathlib.Path("/repo")
        root.mkdir()
        (root / ".dockerignore").write_text("**/a/b/\n")
        result = _ignored_dir_names(root)
        assert "a/b" not in result
        assert "b" not in result

    def test_returns_empty_when_no_dockerignore(self, fs: pyfakefs.fake_filesystem.FakeFilesystem):
        root = pathlib.Path("/repo")
        root.mkdir()
        assert _ignored_dir_names(root) == set()


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
