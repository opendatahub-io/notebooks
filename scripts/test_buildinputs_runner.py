from __future__ import annotations

import pathlib

from scripts import buildinputs_runner


def test_buildinputs_image_uses_repository_slug(monkeypatch, request):
    monkeypatch.delenv("BUILDINPUTS_IMAGE", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "Example/Repo")
    buildinputs_runner._repository_slug.cache_clear()
    request.addfinalizer(buildinputs_runner._repository_slug.cache_clear)

    assert buildinputs_runner.buildinputs_image() == "ghcr.io/example/repo/buildinputs:main"


def test_containarized_buildinputs(monkeypatch):
    captured = {}

    def fake_check_output(command, text, cwd):
        captured["command"] = command
        captured["cwd"] = cwd
        assert text is True
        return '["foo.txt", "bar/baz.txt"]\n'

    monkeypatch.setenv("BUILDINPUTS_RUNTIME", "podman")
    monkeypatch.setenv("BUILDINPUTS_IMAGE", "ghcr.io/example/buildinputs:main")
    monkeypatch.setattr(buildinputs_runner.subprocess, "check_output", fake_check_output)

    stdout = buildinputs_runner.containarized_buildinputs(
        pathlib.Path("jupyter/example/Dockerfile"),
        platform="linux/arm64",
        build_args={"BASE_IMAGE": "fake-image"},
    )

    assert stdout == '["foo.txt", "bar/baz.txt"]\n'
    assert captured["cwd"] == buildinputs_runner.ROOT_DIR
    assert captured["command"] == [
        "podman",
        "run",
        "--rm",
        "-e",
        "TARGETPLATFORM=linux/arm64",
        "-v",
        f"{buildinputs_runner.ROOT_DIR}:{buildinputs_runner.ROOT_DIR}:ro,z",
        "-w",
        str(buildinputs_runner.ROOT_DIR),
        "ghcr.io/example/buildinputs:main",
        "-build-arg=BASE_IMAGE=fake-image",
        str((buildinputs_runner.ROOT_DIR / "jupyter/example/Dockerfile").resolve()),
    ]


def test_local_buildinputs(monkeypatch, tmp_path):
    captured = {}

    fake_binary = tmp_path / "bin" / "buildinputs"
    fake_binary.parent.mkdir()
    fake_binary.touch()

    def fake_check_output(command, text, cwd, env=None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        assert text is True
        return '["foo.txt"]\n'

    monkeypatch.setattr(buildinputs_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(buildinputs_runner.subprocess, "check_output", fake_check_output)

    stdout = buildinputs_runner.local_buildinputs(
        "jupyter/example/Dockerfile",
        platform="linux/amd64",
        build_args={"BASE_IMAGE": "fake-image"},
    )

    assert stdout == '["foo.txt"]\n'
    assert captured["command"] == [
        fake_binary,
        "-build-arg=BASE_IMAGE=fake-image",
        "jupyter/example/Dockerfile",
    ]
    assert captured["env"]["TARGETPLATFORM"] == "linux/amd64"


def test_buildinputs_dispatches_to_container_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(
        buildinputs_runner, "containarized_buildinputs", lambda *a, **kw: '["a.txt"]\n'
    )

    result = buildinputs_runner.buildinputs("Dockerfile")
    assert result == [pathlib.Path("a.txt")]


def test_buildinputs_dispatches_to_local_outside_ci(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(
        buildinputs_runner, "local_buildinputs", lambda *a, **kw: '["b.txt"]\n'
    )

    result = buildinputs_runner.buildinputs("Dockerfile")
    assert result == [pathlib.Path("b.txt")]
