"""Build curated release archive for Rikugan IDA plugin (HCLI flat-ZIP layout).

Chỉ include runtime files cần để install và chạy plugin trong IDA:
- rikugan_plugin.py  (entry point)
- rikugan/           (Python package, loại __pycache__)
- install.sh, install_ida.sh, install.ps1, install_ida.bat
- requirements.txt
- ida-plugin.json
- LICENSE
- README.md

Không include: tests/, docs/, AGENTS.md, ARCHITECTURE.md, DEVELOPMENT.md,
llms.txt, .github/, assets/, chat_examples/, webpage/, pyproject.toml,
uv.lock, ci-local.sh, .git/, .venv/, .*_cache/, __pycache__/.

HCLI layout (per https://hcli.docs.hex-rays.com/reference/plugin-packaging-and-format/):
ida-plugin.json và entryPoint phải ở GỐC zip, không có subfolder bao quanh.

Usage:
    python scripts/build_release.py --version 1.2.3 --out-dir dist

Output:
    dist/rikugan-v1.2.3.zip
    dist/SHA256SUMS
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

# Tên file/dir cần include (paths tương đối so với source root).
INCLUDE_PATHS: list[str] = [
    "rikugan_plugin.py",
    "rikugan",  # toàn bộ package
    "install.sh",
    "install_ida.sh",
    "install.ps1",
    "install_ida.bat",
    "requirements.txt",
    "ida-plugin.json",
    "LICENSE",
    "README.md",
]

# File/dir KHÔNG được include dù nằm trong INCLUDE_PATHS (match bất kỳ path part nào).
EXCLUDE_NAMES: set[str] = {
    "__pycache__",
    ".git",
    ".venv",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".desloppify",
    ".codegraph",
    ".reasonix",
    ".claude",
    "node_modules",
}

# File suffix KHÔNG được include.
EXCLUDE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo", ".pyd")


def should_skip(path: Path) -> bool:
    """Return True nếu path nên bị skip (exclude rule match)."""
    if any(part in EXCLUDE_NAMES for part in path.parts):
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def collect(source_root: Path) -> list[Path]:
    """Collect tất cả files trong INCLUDE_PATHS, áp dụng exclude rules.

    Returns:
        Sorted list of absolute paths to files (sorted by relative
        POSIX path so order is deterministic on Windows and matches
        the Linux CI).
    """
    collected: list[Path] = []
    for spec in INCLUDE_PATHS:
        src = source_root / spec
        if src.is_file():
            if not should_skip(src):
                collected.append(src)
        elif src.is_dir():
            for p in src.rglob("*"):
                if p.is_file() and not should_skip(p):
                    collected.append(p)
        # Nếu spec không tồn tại → silently skip
    return sorted(collected, key=lambda p: p.relative_to(source_root).as_posix())


def build_zip(files: list[Path], out_path: Path, source_root: Path) -> None:
    """Build FLAT zip archive (HCLI layout) — no wrapping subfolder.

    Each file's path inside the archive is its path relative to
    ``source_root`` (forward slashes via ``as_posix()``). ``ida-plugin.json``
    and the entryPoint file end up at the ZIP root.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in files:
            arcname = src.relative_to(source_root).as_posix()
            zf.write(src, arcname)


# ── Stubs filled in by Task 3 ─────────────────────────────────────────


def sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest của file."""
    raise NotImplementedError


def write_sha256sums(paths: list[Path], out_path: Path) -> None:
    """Write SHA256SUMS file (GNU coreutils format)."""
    raise NotImplementedError


def main() -> int:
    """CLI entry point. See module docstring."""
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
