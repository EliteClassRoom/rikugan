"""Regression test for IDA 9.1 QVBoxLayout/PySide6 crash.

Crash symptom (before fix):
    TypeError: arguments did not match any overloaded call:
      QVBoxLayout(QWidget): argument 1 has unexpected type 'PySide6.QtWidgets.QWidget'

Root cause: panel.OnCreate branched on QT_BINDING and could select
FormToPyQtWidget; on IDA 9.x that method returns a PySide6 widget
(since IDA's PyQt5 is a shim), mismatching a PyQt5 QVBoxLayout.

This test pins the contract: OnCreate always uses FormToPySideWidget.

The second test (``test_path_a_dispatches_to_pyqt_under_buggy_branch``)
is a *characterization* test for path (a) of the pre-Task-5 branch:

    if QT_BINDING == "PyQt5":
        self._form_widget = self.FormToPyQtWidget(form)   # ← BUG (path a)

On current ``master`` this test PASSES — proving path (a) calls the wrong
method. After Task 5 removes the ``if QT_BINDING == "PyQt5"`` branch
entirely, ``FormToPyQtWidget`` will no longer be called regardless of the
``QT_BINDING`` value, and this test will FAIL. At that point the Task 5
implementer must FLIP both assertions (pyside.assert_called /
pyqt.assert_not_called) to match the new correct behavior.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from unittest import mock
from unittest.mock import MagicMock

# Make ``tests`` importable and install the IDA + Qt stubs BEFORE any
# ``rikugan.ida.ui.*`` import. ``rikugan.ida.ui.panel`` pulls in
# ``idaapi`` (via ``tools_form``) at module load time; without these
# stubs the import raises ``ModuleNotFoundError`` outside IDA Pro.
# This mirrors the established pattern in ``tests/tools/test_ida_panel.py``.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from tests.qt_stubs import _qt_class, ensure_pyside6_stubs  # noqa: E402

ensure_pyside6_stubs()

# ``rikugan.ida.ui.panel`` also imports these siblings at load time; stub
# them so the module import succeeds without their heavy transitive deps.
_panel_core_mod = types.ModuleType("rikugan.ui.panel_core")
_panel_core_mod.RikuganPanelCore = _qt_class("RikuganPanelCore")
sys.modules.setdefault("rikugan.ui.panel_core", _panel_core_mod)

_session_mod = types.ModuleType("rikugan.ida.ui.session_controller")
_session_mod.IdaSessionController = MagicMock()
sys.modules.setdefault("rikugan.ida.ui.session_controller", _session_mod)

_actions_mod = types.ModuleType("rikugan.ida.ui.actions")
_actions_mod.RikuganUIHooks = MagicMock()
sys.modules.setdefault("rikugan.ida.ui.actions", _actions_mod)


def _run_oncreate_under_stubs(qt_binding: str) -> tuple[mock.MagicMock, mock.MagicMock]:
    """Run ``RikuganPanel.OnCreate`` under the standard stub setup.

    Monkey-patches ``rikugan.ida.ui.panel.QT_BINDING`` (the symbol
    imported by ``panel.py`` at module load) so each test can drive the
    ``if QT_BINDING == "PyQt5"`` branch independently of the host's
    detected binding. Returns ``(pyside_mock, pyqt_mock)`` so callers can
    assert which conversion method OnCreate selected.

    The function exits cleanly even if OnCreate raises partway through
    — the stub setup swallows theme/font work that depends on a real
    IDA runtime; we only care which ``FormTo*Widget`` was invoked.
    """
    panel_mod = importlib.import_module("rikugan.ida.ui.panel")
    panel = panel_mod.RikuganPanel.__new__(panel_mod.RikuganPanel)

    with (
        mock.patch.object(panel_mod, "QT_BINDING", qt_binding),
        mock.patch.object(panel, "FormToPySideWidget", create=True) as pyside,
        mock.patch.object(panel, "FormToPyQtWidget", create=True) as pyqt,
    ):
        # The idaapi.PluginForm base provides these as instance methods;
        # create=True lets us patch them even if the real base is stubbed.
        with (
            mock.patch.object(panel_mod.RikuganPanel, "FormToPySideWidget", pyside),
            mock.patch.object(panel_mod.RikuganPanel, "FormToPyQtWidget", pyqt),
        ):
            # OnCreate constructs QWidget/QVBoxLayout/RikuganPanelCore —
            # stub them via qt_compat so no real Qt is needed.
            from rikugan.ui import qt_compat

            with (
                mock.patch.object(qt_compat, "QWidget", return_value=mock.MagicMock()),
                mock.patch.object(qt_compat, "QVBoxLayout", return_value=mock.MagicMock()),
            ):
                # RikuganPanelCore.__init__ is heavy; short-circuit it.
                with mock.patch("rikugan.ui.panel_core.RikuganPanelCore") as core_cls:
                    core_cls.return_value = mock.MagicMock()
                    try:
                        panel.OnCreate(mock.sentinel.form)
                    except Exception:
                        # OnCreate may do theme work that fails without IDA;
                        # we only care about which Form method was selected.
                        pass

    return pyside, pyqt


class TestPanelOnCreatePySideOnly(unittest.TestCase):
    def test_uses_form_to_pyside_widget_only(self) -> None:
        """Default QT_BINDING (PySide6) path picks FormToPySideWidget.

        Covers OnCreate's ``else`` branch (path b's success branch):
        ``QT_BINDING != "PyQt5"`` → ``FormToPySideWidget(form)``.
        """
        pyside, pyqt = _run_oncreate_under_stubs(qt_binding="PySide6")

        pyside.assert_called()
        pyqt.assert_not_called()

    def test_path_a_dispatches_to_pyqt_under_buggy_branch(self) -> None:
        """QT_BINDING == "PyQt5" path picks FormToPyQtWidget (pre-fix bug).

        Characterization test for path (a) of the pre-Task-5 branch:
        ``if QT_BINDING == "PyQt5": self.FormToPyQtWidget(form)``. On
        ``master`` (before Task 5) this branch is reached when
        ``_detect_binding`` wrongly returns ``"PyQt5"`` because another
        plugin pre-imported PyQt5. Calling ``FormToPyQtWidget`` on
        IDA 9.x returns a PySide6 widget (IDA's PyQt5 is a shim),
        mismatching a PyQt5 ``QVBoxLayout`` and crashing.

        This test PASSES today, pinning the buggy behavior. After Task 5
        drops the ``if QT_BINDING == "PyQt5"`` branch, this assertion
        must be FLIPPED (pyside.assert_called /
        pyqt.assert_not_called) to match the new correct behavior.
        """
        pyside, pyqt = _run_oncreate_under_stubs(qt_binding="PyQt5")

        pyqt.assert_called()
        pyside.assert_not_called()


if __name__ == "__main__":
    unittest.main()
