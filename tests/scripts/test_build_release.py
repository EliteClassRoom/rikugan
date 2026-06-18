"""Unit tests for scripts/build_release.py.

AAA pattern. Uses pytest's ``tmp_path`` fixture to seed a fake repo
layout that mirrors the real project, then runs ``collect()`` /
``build_zip()`` / etc. and asserts on the output.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.build_release import (
    EXCLUDE_NAMES,
    INCLUDE_PATHS,
    build_zip,
    collect,
    sha256_file,
    should_skip,
    write_sha256sums,
)


# ── should_skip ────────────────────────────────────────────────────────


def test_should_skip_excludes_pycache_directory(tmp_path: Path) -> None:
    # Arrange
    p = tmp_path / "rikugan" / "core" / "__pycache__" / "config.cpython-311.pyc"

    # Act
    result = should_skip(p)

    # Assert
    assert result is True


def test_should_skip_excludes_dotfiles_in_path(tmp_path: Path) -> None:
    # Arrange
    p = tmp_path / ".venv" / "lib" / "foo.py"

    # Act
    result = should_skip(p)

    # Assert
    assert result is True


def test_should_skip_excludes_pyc_suffix(tmp_path: Path) -> None:
    # Arrange
    p = tmp_path / "rikugan" / "core" / "config.pyc"

    # Act
    result = should_skip(p)

    # Assert
    assert result is True


def test_should_skip_allows_normal_file(tmp_path: Path) -> None:
    # Arrange
    p = tmp_path / "rikugan" / "core" / "config.py"

    # Act
    result = should_skip(p)

    # Assert
    assert result is False


# ── collect ────────────────────────────────────────────────────────────


def _seed_fake_repo(root: Path) -> None:
    """Mimic the real repo layout: runtime files, dev files, junk files."""
    # Runtime files (must be included)
    (root / "rikugan_plugin.py").write_text("# plugin entry", encoding="utf-8")
    (root / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (root / "install_ida.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (root / "install.ps1").write_text("# ps1\n", encoding="utf-8")
    (root / "install_ida.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "requirements.txt").write_text("anthropic>=0.39.0\n", encoding="utf-8")
    (root / "ida-plugin.json").write_text(
        '{"plugin":{"version":"1.2.3","entryPoint":"rikugan_plugin.py"}}\n', encoding="utf-8"
    )
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "README.md").write_text("# Rikugan\n", encoding="utf-8")
    # rikugan/ package (must be included, recursively)
    (root / "rikugan").mkdir()
    (root / "rikugan" / "__init__.py").write_text("", encoding="utf-8")
    (root / "rikugan" / "core").mkdir()
    (root / "rikugan" / "core" / "__init__.py").write_text("", encoding="utf-8")
    (root / "rikugan" / "core" / "config.py").write_text("# config\n", encoding="utf-8")
    # rikugan/skills/builtins/ subdir (real plugin loads from here)
    (root / "rikugan" / "skills").mkdir()
    (root / "rikugan" / "skills" / "builtins").mkdir()
    (root / "rikugan" / "skills" / "builtins" / "ctf").mkdir()
    (root / "rikugan" / "skills" / "builtins" / "ctf" / "SKILL.md").write_text("# ctf\n", encoding="utf-8")
    # Junk that MUST be excluded
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("# test\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("# doc\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "ARCHITECTURE.md").write_text("# arch\n", encoding="utf-8")
    (root / "DEVELOPMENT.md").write_text("# dev\n", encoding="utf-8")
    (root / "llms.txt").write_text("# llms\n", encoding="utf-8")
    (root / ".github").mkdir()
    (root / ".github" / "workflows").mkdir()
    (root / ".github" / "workflows" / "ci.yml").write_text("# ci\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "icon.png").write_bytes(b"\x89PNG")
    (root / "chat_examples").mkdir()
    (root / "chat_examples" / "example.md").write_text("# ex\n", encoding="utf-8")
    (root / "webpage").mkdir()
    (root / "webpage" / "index.html").write_text("<html/>\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("# toml\n", encoding="utf-8")
    (root / "uv.lock").write_text("# lock\n", encoding="utf-8")
    (root / "ci-local.sh").write_text("# ci script\n", encoding="utf-8")
    # Top-level scripts/ subdir — used so the build_zip tests have
    # >1 top-level dir to assert against (HCLI flat-layout check).
    (root / "scripts").mkdir()
    (root / "scripts" / "build_release.py").write_text("# build\n", encoding="utf-8")
    # Junk inside rikugan/ that MUST be excluded
    (root / "rikugan" / "core" / "__pycache__").mkdir()
    (root / "rikugan" / "core" / "__pycache__" / "config.cpython-311.pyc").write_bytes(b"PYC")
    (root / "rikugan" / ".mypy_cache").mkdir()
    (root / "rikugan" / ".mypy_cache" / "x.json").write_text("{}\n", encoding="utf-8")
    (root / "rikugan" / "core" / "leftover.pyc").write_bytes(b"PYC")


def test_collect_includes_runtime_files(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)

    # Act
    result = collect(tmp_path)

    # Assert: every INCLUDE_PATHS file appears in result
    included = {p.relative_to(tmp_path).as_posix() for p in result}
    for spec in INCLUDE_PATHS:
        if spec in ("rikugan", "scripts"):
            # recursive dirs — covered in other tests
            continue
        assert spec in included, f"expected {spec!r} in collect() output"


def test_collect_includes_nested_runtime_files(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)

    # Act
    result = collect(tmp_path)

    # Assert: nested files inside rikugan/ are present
    included = {p.relative_to(tmp_path).as_posix() for p in result}
    assert "rikugan/__init__.py" in included
    assert "rikugan/core/config.py" in included
    assert "rikugan/skills/builtins/ctf/SKILL.md" in included


def test_collect_excludes_tests_and_docs(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)

    # Act
    result = collect(tmp_path)

    # Assert
    included = {p.relative_to(tmp_path).as_posix() for p in result}
    assert "tests/test_x.py" not in included
    assert "docs/x.md" not in included
    assert "AGENTS.md" not in included
    assert "ARCHITECTURE.md" not in included
    assert "DEVELOPMENT.md" not in included
    assert "llms.txt" not in included


def test_collect_excludes_dev_assets_and_config(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)

    # Act
    result = collect(tmp_path)

    # Assert
    included = {p.relative_to(tmp_path).as_posix() for p in result}
    assert "assets/icon.png" not in included
    assert "chat_examples/example.md" not in included
    assert "webpage/index.html" not in included
    assert "pyproject.toml" not in included
    assert "uv.lock" not in included
    assert "ci-local.sh" not in included
    assert ".github/workflows/ci.yml" not in included


def test_collect_excludes_pycache_and_dotfiles(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)

    # Act
    result = collect(tmp_path)

    # Assert
    included = {p.relative_to(tmp_path).as_posix() for p in result}
    assert "rikugan/core/__pycache__/config.cpython-311.pyc" not in included
    assert "rikugan/core/leftover.pyc" not in included
    assert "rikugan/.mypy_cache/x.json" not in included


def test_collect_returns_sorted_output(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)

    # Act
    result = collect(tmp_path)

    # Assert
    rel = [p.relative_to(tmp_path).as_posix() for p in result]
    assert rel == sorted(rel)


def test_collect_handles_missing_specs_gracefully(tmp_path: Path) -> None:
    # Arrange: a bare-minimum repo with no rikugan/ package
    (tmp_path / "rikugan_plugin.py").write_text("#\n", encoding="utf-8")

    # Act
    result = collect(tmp_path)

    # Assert: doesn't crash; just collects what exists
    included = {p.relative_to(tmp_path).as_posix() for p in result}
    assert "rikugan_plugin.py" in included


# ── build_zip (HCLI flat layout) ──────────────────────────────────────


def test_build_zip_creates_valid_archive(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world", encoding="utf-8")
    out = tmp_path / "out.zip"
    files = [tmp_path / "a.txt", tmp_path / "sub" / "b.txt"]

    # Act
    build_zip(files, out, tmp_path)

    # Assert
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "a.txt" in names
    assert "sub/b.txt" in names


def test_build_zip_ida_plugin_json_at_root(tmp_path: Path) -> None:
    # Arrange — simulate the real plugin layout
    _seed_fake_repo(tmp_path)
    files = collect(tmp_path)
    out = tmp_path / "out.zip"

    # Act
    build_zip(files, out, tmp_path)

    # Assert: ida-plugin.json is a top-level entry (HCLI contract)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "ida-plugin.json" in names, f"ida-plugin.json not at root; got {names[:5]}"


def test_build_zip_entry_point_at_root(tmp_path: Path) -> None:
    # Arrange
    _seed_fake_repo(tmp_path)
    files = collect(tmp_path)
    out = tmp_path / "out.zip"

    # Act
    build_zip(files, out, tmp_path)

    # Assert: the entryPoint file (rikugan_plugin.py) is a top-level entry
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "rikugan_plugin.py" in names


def test_build_zip_no_wrapping_subfolder(tmp_path: Path) -> None:
    # Arrange — HCLI requires flat layout; reject any wrapping subfolder
    _seed_fake_repo(tmp_path)
    files = collect(tmp_path)
    out = tmp_path / "out.zip"

    # Act
    build_zip(files, out, tmp_path)

    # Assert: no entry begins with a single wrapping prefix like "rikugan-v1.2.3/"
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    wrapping = [n for n in names if "/" in n and not n.startswith(("rikugan/", "install", "scripts/"))]
    # entries like "rikugan/core/config.py" are fine (real subdir); only a SINGLE
    # common prefix on every entry would indicate a wrapping subfolder
    import os.path

    top_dirs = {n.split("/")[0] for n in names if "/" in n}
    # If there is exactly ONE top-level dir wrapping everything, that's the bug.
    assert len(top_dirs) > 1, f"single wrapping subfolder detected: {top_dirs}"


def test_build_zip_preserves_file_contents(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "x.py").write_text("secret content 12345\n", encoding="utf-8", newline="")
    out = tmp_path / "out.zip"

    # Act
    build_zip([tmp_path / "x.py"], out, tmp_path)

    # Assert
    with zipfile.ZipFile(out) as zf:
        assert zf.read("x.py") == b"secret content 12345\n"
