"""Backward-compatible panel import path."""

from __future__ import annotations

from ..core.host import is_binary_ninja, is_ida

if is_binary_ninja():
    from ..binja.ui.panel import RikuganPanel
elif is_ida():
    from ..ida.ui.panel import RikuganPanel
else:
    from .panel_core import RikuganPanelCore as RikuganPanel  # noqa: F401
