"""Run an arbitrary callable inside a fresh Python subprocess.

The worker is used by ``tests/ida/test_emulation.py`` to keep Unicorn's
ctypes state isolated per scenario. Each invocation boots a brand-new
interpreter, runs ``tests.<module>`` with a JSON payload forwarded via
stdin, and captures the JSON-encoded result on stdout. Stdin avoids
the Windows command-line length limit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_in_subprocess(module: str, payload: str, *, timeout: float = 30.0) -> Any:
    """Spawn ``python -m tests.<module>`` and feed *payload* via stdin."""

    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT
    proc = subprocess.run(
        [sys.executable, "-m", module],
        cwd=REPO_ROOT,
        env=env,
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"subprocess failed (rc={proc.returncode}):\n  stdout=\n{proc.stdout}\n  stderr=\n{proc.stderr}"
        )
    out = proc.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"subprocess returned invalid JSON: {out!r}") from e
