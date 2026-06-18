"""Structural validation shim for HCLI plugin archives.

If ``hcli`` is not available on the runner, this module provides a
deterministic Python check that the built ZIP is HCLI-compliant:

- ``ida-plugin.json`` is at the ZIP root (not nested in a subfolder)
- ``ida-plugin.json`` is valid JSON with a ``plugin.entryPoint`` field
- The ``entryPoint`` file exists at the ZIP root
- No single subfolder wraps every entry

When ``hcli`` IS available, prefer ``hcli plugin lint <zip>`` — it is
authoritative. This shim is the fallback.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


class ArchiveValidationError(Exception):
    """Raised when a ZIP is not HCLI-compliant."""


def validate_archive(zip_path: Path) -> None:
    """Validate that ``zip_path`` is an HCLI-compliant plugin archive.

    Raises:
        ArchiveValidationError: if any HCLI contract is violated.
    """
    if not zip_path.is_file():
        raise ArchiveValidationError(f"archive not found: {zip_path}")

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    # 1. ida-plugin.json must be a top-level entry
    if "ida-plugin.json" not in names:
        raise ArchiveValidationError(
            "ida-plugin.json not found at the archive root "
            f"(got top-level entries: {sorted({n.split('/')[0] for n in names})})"
        )

    # 2. No single subfolder wraps everything
    top_levels = {n.split("/")[0] for n in names}
    if len(top_levels) == 1 and next(iter(top_levels)) != "ida-plugin.json":
        # Everything is under one dir — that's a wrapping subfolder
        raise ArchiveValidationError(
            f"archive appears wrapped in a single subfolder: {top_levels}; "
            "HCLI requires ida-plugin.json at the archive root"
        )

    # 3. ida-plugin.json must be valid JSON with plugin.entryPoint
    with zipfile.ZipFile(zip_path) as zf:
        try:
            meta = json.loads(zf.read("ida-plugin.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ArchiveValidationError(f"ida-plugin.json is not valid JSON: {e}") from e

    plugin = meta.get("plugin") if isinstance(meta, dict) else None
    if not isinstance(plugin, dict):
        raise ArchiveValidationError("ida-plugin.json missing 'plugin' object")
    entry_point = plugin.get("entryPoint")
    if not entry_point or not isinstance(entry_point, str):
        raise ArchiveValidationError("ida-plugin.json missing 'plugin.entryPoint' string")

    # 4. The entryPoint file must exist at the ZIP root
    if entry_point not in names:
        raise ArchiveValidationError(
            f"entryPoint {entry_point!r} not found in archive root (HCLI requires the entry file at the root)"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: validate_archive.py <zip-path>", file=sys.stderr)
        sys.exit(2)
    try:
        validate_archive(Path(sys.argv[1]))
    except ArchiveValidationError as e:
        print(f"INVALID: {e}", file=sys.stderr)
        sys.exit(1)
    print("OK")
