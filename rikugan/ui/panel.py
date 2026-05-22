"""IDA Pro panel import path."""

from __future__ import annotations

from ..core.host import is_ida

if is_ida():
    from ..ida.ui.panel import RikuganPanel
else:
    from .panel_core import RikuganPanelCore as RikuganPanel  # noqa: F401
