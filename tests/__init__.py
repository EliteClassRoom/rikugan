"""Shared test helpers.

Currently exposes :func:`purge_rikugan_stubs`, which drops any
``_StubModule`` entries from :data:`sys.modules` so the real
``rikugan.*`` modules are re-imported on the next ``from rikugan...``.

Some sibling test files (notably ``tests/tools/test_panel_core.py``
and ``tests/tools/test_chat_view.py``) install these stubs at module
import time to keep panel-internal tests fast and dependency-free.
The stubs use a ``__getattr__`` fallback that returns a ``MagicMock``
for any unknown name — useful in isolation, but fatal when the stubs
remain in :data:`sys.modules` for downstream test files that need the
real ``rikugan.core.config``, ``rikugan.providers.registry``, and
similar modules.

The function is intentionally narrow: it only removes entries whose
class is named ``_StubModule`` and which live under the
``rikugan.*`` namespace, so real modules are never touched.
"""

from __future__ import annotations

import sys

_RIKUGAN_STUB_NAMES = (
    "rikugan.ui.styles",
    "rikugan.ui.chat_view",
    "rikugan.ui.input_area",
    "rikugan.ui.context_bar",
    "rikugan.ui.tool_widgets",
    "rikugan.ui.message_widgets",
    "rikugan.ui.markdown",
    "rikugan.ui.theme",
    "rikugan.ui.theme.manager",
    "rikugan.ui.theme.tokens",
    "rikugan.ui.theme.palette_dark",
    "rikugan.ui.theme.palette_light",
    "rikugan.ui.theme.palette_ida",
    "rikugan.core.config",
    "rikugan.core.logging",
    "rikugan.core.types",
    "rikugan.core.host",
    "rikugan.agent.turn",
    "rikugan.agent.mutation",
    "rikugan.providers.auth_cache",
    "rikugan.providers.anthropic_provider",
    "rikugan.providers.ollama_provider",
    "rikugan.providers.registry",
)


def purge_rikugan_stubs() -> None:
    """Remove ``_StubModule`` entries from :data:`sys.modules`."""
    for name in _RIKUGAN_STUB_NAMES:
        mod = sys.modules.get(name)
        if mod is None:
            continue
        if mod.__class__.__name__ == "_StubModule":
            del sys.modules[name]
