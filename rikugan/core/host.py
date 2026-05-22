"""Host/runtime detection and context utilities.

This module centralizes runtime integration points so Rikugan can run inside
IDA Pro or standalone Python.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

HOST_IDA = "ida"
HOST_STANDALONE = "standalone"

_HOST = HOST_STANDALONE
_idc = None
_idaapi = None
_ida_kernwin = None
try:
    _idaapi = importlib.import_module("idaapi")
    _HOST = HOST_IDA
    # Cache frequently-used IDA modules to avoid repeated importlib lookups.
    # Both are optional — headless/batch IDA may not expose them.
    try:
        _idc = importlib.import_module("idc")
    except ImportError:
        _idc = None  # optional — absent in some IDA headless configurations
    try:
        _ida_kernwin = importlib.import_module("ida_kernwin")
    except ImportError:
        _ida_kernwin = None  # optional — absent in some IDA headless configurations
except ImportError:
    _HOST = HOST_STANDALONE


def host_kind() -> str:
    """Return the active runtime host: ida or standalone."""
    return _HOST


def is_ida() -> bool:
    return _HOST == HOST_IDA


# Convenience module-level flag — importers that just need a bool
# can use ``from rikugan.core.host import IDA_AVAILABLE`` instead of
# calling ``is_ida()`` repeatedly.
IDA_AVAILABLE: bool = is_ida()

# Whether the Hex-Rays decompiler SDK is importable.
if IDA_AVAILABLE:
    try:
        importlib.import_module("ida_hexrays")
        HAS_HEXRAYS: bool = True
    except ImportError:
        HAS_HEXRAYS = False
else:
    HAS_HEXRAYS = False


def host_display_name() -> str:
    if _HOST == HOST_IDA:
        return "IDA Pro"
    return "Standalone Python"


def get_current_address() -> int | None:
    """Return current cursor/address from host context if available."""
    if is_ida():
        try:
            return int(_idc.get_screen_ea()) if _idc else None
        except Exception:
            return None

    return None


def navigate_to(address: int) -> bool:
    """Navigate UI to an address when the host supports it."""
    ea = int(address)

    if is_ida():
        try:
            return bool(_ida_kernwin.jumpto(ea)) if _ida_kernwin else False
        except Exception:
            return False

    return False


def get_user_config_base_dir() -> str:
    """Return host-specific user base directory for Rikugan config/log files."""
    if is_ida():
        try:
            return _idaapi.get_user_idadir() if _idaapi else os.path.join(str(Path.home()), ".idapro")
        except Exception:
            return os.path.join(str(Path.home()), ".idapro")

    return os.path.join(str(Path.home()), ".idapro")


def get_database_path() -> str:
    """Return the loaded database/binary path for the active host."""
    if is_ida():
        try:
            if _idaapi is None:
                return ""
            idb = _idaapi.get_path(_idaapi.PATH_TYPE_IDB)
            if idb:
                return idb
            return _idaapi.get_input_file_path() or ""
        except Exception:
            return ""

    return ""


def get_database_instance_id() -> str:
    """Read the Rikugan instance UUID stored in the current IDB.

    Returns '' if none is stored yet.
    """
    if is_ida():
        try:
            idaapi = _idaapi
            if idaapi is None:
                return ""
            node = idaapi.netnode("$ rikugan", 0, False)
            if node == idaapi.BADNODE:
                return ""
            val = node.supstr(0)
            return val if isinstance(val, str) and val else ""
        except Exception:
            return ""

    return ""


def set_database_instance_id(instance_id: str) -> bool:
    """Store a Rikugan instance UUID in the current IDB.

    Returns True on success.
    """
    if is_ida():
        try:
            idaapi = _idaapi
            if idaapi is None:
                return False
            node = idaapi.netnode("$ rikugan", 0, True)
            node.supset(0, instance_id)
            return True
        except Exception as e:
            sys.stderr.write(f"[Rikugan] set_database_instance_id IDA failed: {e}\n")
            return False

    return False
