"""Shared PySide6 stub injection for UI tests.

Must be called BEFORE importing any rikugan.ui module. Example::

    from tests.qt_stubs import ensure_pyside6_stubs
    ensure_pyside6_stubs()
    from rikugan.ui.some_module import ...
"""

from __future__ import annotations

import sys
import types

_installed = False


def _qt_class(name: str) -> type:
    """Create a minimal stubbed Qt class that supports subclassing.

    Provides common QWidget / QLayout methods as no-ops so that
    constructor chains (super().__init__ → setObjectName → setStyleSheet)
    succeed without a real Qt runtime.
    """

    def _noop(self, *a, **k):
        return None

    def _visible_getter(self):
        return getattr(self, "_visible", True)

    def _visible_setter(self, val):
        self._visible = val

    def _text_getter(self):
        return getattr(self, "_text", "")

    def _text_setter(self, val):
        self._text = val

    attrs = {
        "__init__": _noop,
        # QWidget common
        "setObjectName": _noop,
        "setStyleSheet": _noop,
        "setMinimumWidth": _noop,
        "setSizePolicy": _noop,
        "setFixedSize": _noop,
        "setWordWrap": _noop,
        "setTextFormat": _noop,
        "setTextInteractionFlags": _noop,
        "setOpenExternalLinks": _noop,
        "setContentsMargins": _noop,
        "setSpacing": _noop,
        "setFixedWidth": _noop,
        "setFixedHeight": _noop,
        "setMaximumHeight": _noop,
        "setAlignment": _noop,
        "setCheckable": _noop,
        "setChecked": _noop,
        "setText": _text_setter,
        "addLayout": _noop,
        "addWidget": _noop,
        "addSpacing": _noop,
        "addStretch": _noop,
        "addItem": _noop,
        "setToolButtonStyle": _noop,
        "setArrowType": _noop,
        "setPopupMode": _noop,
        "setMenu": _noop,
        "setDefault": _noop,
        "clicked": _Signal(),
        "setVisible": _noop,
        "setParent": _noop,
        "setLayout": _noop,
        "resize": _noop,
        "sizeHint": lambda self: None,
        # Geometry helpers for _HeightCachedLabel
        "width": lambda self: 0,
        "heightForWidth": lambda self, w: 0,
        # Visibility with tracking
        "hide": lambda self: setattr(self, "_visible", False),
        "show": lambda self: setattr(self, "_visible", True),
        "isVisible": _visible_getter,
        "close": lambda self: True,
        # Text with tracking
        "text": _text_getter,
    }
    return type(name, (), attrs)


class _Signal:
    """Minimal Signal stub that acts as a descriptor.

    Tracks connected slots in a list and invokes them on emit, so tests
    can verify signal-driven behavior (e.g. ``sig.connect(lambda x: ...)``
    followed by ``sig.emit(value)``). Disconnecting a slot not in the
    list is a no-op, matching PySide6 semantics.
    """

    def __init__(self, *a):
        self._connections: list = []

    def connect(self, slot):
        self._connections.append(slot)

    def disconnect(self, *slots):
        if not slots:
            self._connections.clear()
            return
        for slot in slots:
            if slot in self._connections:
                self._connections.remove(slot)

    def emit(self, *a):
        for slot in self._connections:
            slot(*a)

    def __get__(self, obj, objtype=None):
        return self


_WIDGET_NAMES = [
    "QAbstractItemView",
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QDialog",
    "QDialogButtonBox",
    "QDoubleSpinBox",
    "QFileDialog",
    "QFormLayout",
    "QFrame",
    "QGroupBox",
    "QHBoxLayout",
    "QHeaderView",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMenu",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QRadioButton",
    "QScrollArea",
    "QSizePolicy",
    "QSpinBox",
    "QSplitter",
    "QStackedWidget",
    "QTabBar",
    "QTableWidget",
    "QTableWidgetItem",
    "QTabWidget",
    "QTextEdit",
    "QToolButton",
    "QTreeWidget",
    "QTreeWidgetItem",
    "QVBoxLayout",
    "QWidget",
]

_GUI_NAMES = [
    "QColor",
    "QFont",
    "QIntValidator",
    "QPalette",
    "QSyntaxHighlighter",
    "QTextCharFormat",
]


def _stub_mod(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


def ensure_pyside6_stubs() -> None:
    """Install minimal PySide6 stubs into sys.modules (idempotent)."""
    global _installed
    if _installed:
        return
    _installed = True

    _sentinel = type("_Qt", (), {})()
    _sentinel.ItemDataRole = type("_ItemDataRole", (), {"UserRole": 32})()
    _sentinel.TextFormat = type("_TextFormat", (), {"PlainText": 0, "RichText": 1, "AutoText": 2})()
    _sentinel.TextInteractionFlag = type(
        "_TextInteractionFlag", (),
        {
            "NoTextInteraction": 0,
            "TextSelectableByMouse": 1,
            "TextSelectableByKeyboard": 2,
            "TextEditable": 4,
            "TextEditorInteraction": 6,
            "TextBrowserInteraction": 13,
            "LinksAccessibleByMouse": 8,
            "LinksAccessibleByKeyboard": 16,
        },
    )()
    _sentinel.AlignmentFlag = type(
        "_AlignmentFlag", (),
        {
            "AlignLeft": 1, "AlignRight": 2, "AlignHCenter": 4,
            "AlignTop": 32, "AlignBottom": 64, "AlignVCenter": 128,
            "AlignCenter": 132, "AlignAbsolute": 16, "AlignLeading": 1,
            "AlignTrailing": 2,
        },
    )()
    _sentinel.Orientation = type(
        "_Orientation", (), {"Horizontal": 1, "Vertical": 2}
    )()

    sys.modules.setdefault("PySide6", _stub_mod("PySide6"))
    sys.modules.setdefault(
        "PySide6.QtCore",
        _stub_mod(
            "PySide6.QtCore",
            Signal=_Signal,
            QEvent=_qt_class("QEvent"),
            Qt=_sentinel,
            QObject=_qt_class("QObject"),
            QTimer=_qt_class("QTimer"),
        ),
    )

    # QSizePolicy needs nested Policy enum
    _size_policy = _qt_class("QSizePolicy")
    _size_policy.Policy = type(
        "_SizePolicyPolicy", (),
        {
            "Fixed": 0, "Minimum": 1, "Maximum": 4, "Preferred": 5,
            "Expanding": 7, "MinimumExpanding": 3, "Ignored": 13,
        },
    )()

    # QFont needs a nested Weight enum (QFont.Weight.Bold) so the syntax
    # highlighter can mark keywords as bold without hitting AttributeError.
    _qfont = _qt_class("QFont")
    _qfont.Weight = type(
        "_QFontWeight", (),
        {
            "Thin": 0, "ExtraLight": 12, "Light": 25, "Normal": 50, "Medium": 63,
            "DemiBold": 75, "Bold": 75, "ExtraBold": 81, "Black": 87,
        },
    )()

    _widget_stubs = {n: _qt_class(n) for n in _WIDGET_NAMES}
    _widget_stubs["QSizePolicy"] = _size_policy
    # QFont lives under QtGui, but we build it here so we can attach the
    # nested Weight enum before exposing it to the module below.
    sys.modules.setdefault(
        "PySide6.QtGui",
        _stub_mod(
            "PySide6.QtGui",
            **{n: _qt_class(n) for n in _GUI_NAMES},
        ),
    )
    sys.modules["PySide6.QtGui"].QFont = _qfont

    sys.modules.setdefault(
        "PySide6.QtWidgets",
        _stub_mod("PySide6.QtWidgets", **_widget_stubs),
    )

    # Replace QColor and QTextCharFormat with state-tracking stubs so the
    # syntax highlighter test can verify that palette colours flow through
    # to the QTextCharFormat foreground property. Plain `_qt_class` stubs
    # would be no-ops and swallow the colour information.
    def _qcolor_init(self, name=""):
        self._name = str(name).lower()

    def _qcolor_name(self):
        return self._name

    def _qtext_char_format_init(self):
        self._fg = _qcolor("")
        self._bold = False
        self._italic = False

    def _qtext_char_format_set_foreground(self, c):
        self._fg = c

    def _qtext_char_format_foreground(self):
        return self._fg

    def _qtext_char_format_set_font_weight(self, w):
        self._bold = w

    def _qtext_char_format_set_font_italic(self, i):
        self._italic = bool(i)

    def _qtext_char_format_font_italic(self):
        return self._italic

    def _qtext_char_format_font_weight(self):
        return self._bold

    _qcolor = type(
        "QColor",
        (),
        {
            "__init__": _qcolor_init,
            "name": _qcolor_name,
        },
    )
    _qtext_char_format = type(
        "QTextCharFormat",
        (),
        {
            "__init__": _qtext_char_format_init,
            "setForeground": _qtext_char_format_set_foreground,
            "foreground": _qtext_char_format_foreground,
            "setFontWeight": _qtext_char_format_set_font_weight,
            "fontWeight": _qtext_char_format_font_weight,
            "setFontItalic": _qtext_char_format_set_font_italic,
            "fontItalic": _qtext_char_format_font_italic,
        },
    )
    sys.modules["PySide6.QtGui"].QColor = _qcolor
    sys.modules["PySide6.QtGui"].QTextCharFormat = _qtext_char_format
