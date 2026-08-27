from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "lockfile-generators" / "helpers" / "pylock-to-requirements.py"
_SPEC = importlib.util.spec_from_file_location("pylock_to_requirements", _MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
helper = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(helper)


def test_extract_default_index_from_pylock_strips_format_json(tmp_path: Path) -> None:
    pylock_path = tmp_path / "pylock.toml"
    pylock_path.write_text(
        "# uv pip compile --default-index=https://example.invalid/simple/?format=json\n",
        encoding="utf-8",
    )

    assert helper.extract_default_index_from_pylock(pylock_path) == "https://example.invalid/simple/"


def test_wheel_is_el9_compatible() -> None:
    assert helper.wheel_is_el9_compatible(
        "https://example.invalid/uv-0.12.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    )
    assert helper.wheel_is_el9_compatible("pkg-1.0-py3-none-any.whl")
    assert helper.wheel_is_el9_compatible("pkg-1.0-cp312-cp312-manylinux2010_x86_64.whl")
    assert helper.wheel_is_el9_compatible("pkg-1.0-cp312-cp312-manylinux_2_34_x86_64.whl")
    assert not helper.wheel_is_el9_compatible("pkg-1.0-cp312-cp312-manylinux_2_35_x86_64.whl")
    assert not helper.wheel_is_el9_compatible("ripgrep-15.1.0-py3-none-manylinux_2_39_x86_64.whl")
    assert not helper.wheel_is_el9_compatible("pkg-1.0-py3-none-musllinux_1_1_x86_64.whl")
    assert not helper.wheel_is_el9_compatible("manylinux2010_helper-1.0-cp312-cp312-manylinux_2_39_x86_64.whl")
    assert not helper.wheel_is_el9_compatible("not-a-wheel.tar.gz")


def test_collect_index_hashes_omits_sdist_when_el9_wheel_exists() -> None:
    pkg = {
        "wheels": [
            {
                "url": "https://example.invalid/uv-0.12.5-py3-none-manylinux_2_17_x86_64.whl",
                "hashes": {"sha256": "wheelhash"},
            }
        ],
        "sdist": {
            "url": "https://example.invalid/uv-0.12.5.tar.gz",
            "hashes": {"sha256": "sdisthash"},
        },
    }
    assert helper.collect_index_hashes(pkg) == ["--hash=sha256:wheelhash"]


def test_collect_index_hashes_keeps_sdist_without_el9_wheel() -> None:
    pkg = {
        "wheels": [
            {
                "url": "https://example.invalid/ripgrep-15.1.0-py3-none-manylinux_2_39_x86_64.whl",
                "hashes": {"sha256": "wheelhash"},
            }
        ],
        "sdist": {
            "url": "https://example.invalid/ripgrep-15.1.0.tar.gz",
            "hashes": {"sha256": "sdisthash"},
        },
    }
    assert helper.collect_index_hashes(pkg) == [
        "--hash=sha256:wheelhash",
        "--hash=sha256:sdisthash",
    ]


def test_collect_index_hashes_omits_sdist_if_any_el9_wheel_exists() -> None:
    """A too-new amd64 wheel must not hide an EL9 aarch64 wheel (or vice versa)."""
    pkg = {
        "wheels": [
            {
                "url": "https://example.invalid/pkg-1.0-py3-none-manylinux_2_39_x86_64.whl",
                "hashes": {"sha256": "newamd64"},
            },
            {
                "url": "https://example.invalid/pkg-1.0-py3-none-manylinux_2_17_aarch64.whl",
                "hashes": {"sha256": "el9arm"},
            },
        ],
        "sdist": {
            "url": "https://example.invalid/pkg-1.0.tar.gz",
            "hashes": {"sha256": "sdisthash"},
        },
    }
    assert helper.collect_index_hashes(pkg) == [
        "--hash=sha256:newamd64",
        "--hash=sha256:el9arm",
    ]


def test_collect_index_hashes_sdist_only() -> None:
    pkg = {
        "sdist": {
            "url": "https://example.invalid/pkg-1.0.tar.gz",
            "hashes": {"sha256": "sdisthash"},
        }
    }
    assert helper.collect_index_hashes(pkg) == ["--hash=sha256:sdisthash"]


def test_collect_index_hashes_prefer_omits_sdist_when_el9_wheel_exists() -> None:
    """``prefer`` must not emit sdist hashes when an EL9 wheel exists.

    GHA ``pylocks_generator`` still passes ``--sdist-hashes prefer`` for
    public-index images. Including those sdists makes Hermeto run
    ``cargo vendor`` on incomplete Rust sdists (ripgrep) and fail prefetch.
    """
    pkg = {
        "wheels": [
            {
                "url": "https://example.invalid/ripgrep-14.1.0-py3-none-manylinux_2_17_x86_64.whl",
                "hashes": {"sha256": "wheelhash"},
            }
        ],
        "sdist": {
            "url": "https://example.invalid/ripgrep-14.1.0.tar.gz",
            "hashes": {"sha256": "sdisthash"},
        },
    }
    assert helper.collect_index_hashes(pkg, sdist_hashes=helper.SDIST_HASHES_PREFER) == [
        "--hash=sha256:wheelhash",
    ]


def test_collect_index_hashes_prefer_sdist_only() -> None:
    pkg = {
        "sdist": {
            "url": "https://example.invalid/pkg-1.0.tar.gz",
            "hashes": {"sha256": "sdisthash"},
        }
    }
    assert helper.collect_index_hashes(pkg, sdist_hashes=helper.SDIST_HASHES_PREFER) == [
        "--hash=sha256:sdisthash",
    ]
