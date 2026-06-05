from __future__ import annotations

import json
from pathlib import Path

from rikugan.constants import PLUGIN_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_version_matches_project_metadata() -> None:
    ida_plugin_json = json.loads((ROOT / "ida-plugin.json").read_text(encoding="utf-8"))

    assert PLUGIN_VERSION == ida_plugin_json["plugin"]["version"], (
        f"constants.py ({PLUGIN_VERSION}) != ida-plugin.json ({ida_plugin_json['plugin']['version']})"
    )
