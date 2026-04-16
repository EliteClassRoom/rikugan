"""Rikugan Binary Ninja plugin package bootstrap.

Binary Ninja's plugin loader requires a root ``__init__.py`` when loading
from a directory.  This file is intentionally minimal — all runtime
orchestration lives in ``rikugan.binja.bootstrap``.
"""

try:
    import binaryninja  # type: ignore[import-not-found]  # noqa: F401
except Exception:
    binaryninja = None

if binaryninja is not None:
    from . import rikugan_binaryninja  # noqa: F401
