"""message_widgets and tool_widgets must not use qt_flags."""

from __future__ import annotations

import pathlib
import unittest

_FILES = [
    pathlib.Path("rikugan/ui/message_widgets.py"),
    pathlib.Path("rikugan/ui/tool_widgets.py"),
]


class TestNoQtFlagsHelpers(unittest.TestCase):
    def test_no_qt_flags_references(self) -> None:
        for f in _FILES:
            with self.subTest(file=str(f)):
                source = f.read_text(encoding="utf-8")
                self.assertNotIn(
                    "qt_flags",
                    source,
                    f"{f}: qt_flags must be inlined as `|`",
                )


if __name__ == "__main__":
    unittest.main()
