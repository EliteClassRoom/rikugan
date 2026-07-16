"""Tests for central memory config, constants, and dependency manifests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from rikugan.core.config import RikuganConfig


def test_memory_dir_is_central(tmp_path: Path) -> None:
    config = RikuganConfig()
    config._config_dir = str(tmp_path)

    assert Path(config.memory_dir) == tmp_path / "memory"


def test_portalocker_runtime_dependency_is_in_all_manifests() -> None:
    root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = json.loads((root / "ida-plugin.json").read_text(encoding="utf-8"))
    requirements = {
        line.strip()
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    project_deps = set(pyproject["project"]["dependencies"])
    plugin_deps = set(plugin["plugin"]["pythonDependencies"])
    expected = "portalocker>=3.0.0,<4"

    assert expected in project_deps
    assert expected in plugin_deps
    assert expected in requirements
