"""IDA session controller — canonical import location.

Re-exports ``IdaSessionController`` from its primary home in
``rikugan.ida.ui.session_controller`` so that non-UI code (headless,
tests) can import the controller without touching the ``ui`` package.
"""

from __future__ import annotations

# Re-export from the canonical location (which lives under ui/ for
# historical reasons but is itself Qt-free).
from .ui.session_controller import (
    IdaSessionController,
)
from .ui.session_controller import (
    SessionController as SessionControllerCompat,
)

__all__ = ["IdaSessionController", "SessionControllerCompat"]
