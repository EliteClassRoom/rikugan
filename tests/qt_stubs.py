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
        "setMinimumSize": _noop,
        "setSizePolicy": _noop,
        "setFixedSize": _noop,
        "setFixedWidth": _noop,
        "setWordWrap": _noop,
        "setSingleStep": _noop,
        "setValue": _noop,
        "setEnabled": _noop,
        "setTextFormat": _noop,
        "setTextInteractionFlags": _noop,
        "setOpenExternalLinks": _noop,
        "setContentsMargins": _noop,
        "setSpacing": _noop,
        "setFixedHeight": _noop,
        "setMaximumHeight": _noop,
        "setCheckable": _noop,
        "setChecked": _noop,
        "setText": _text_setter,
        "setToolTip": _noop,
        "setStatusTip": _noop,
        "setWhatsThis": _noop,
        "addLayout": _noop,
        "addWidget": _noop,
        "addStretch": _noop,
        "addItem": _noop,
        "setToolButtonStyle": _noop,
        "setArrowType": _noop,
        "setPopupMode": _noop,
        "setDefault": _noop,
        "setDisabled": _noop,
        "setHidden": _noop,
        "setIcon": _noop,
        "setPlaceholderText": _noop,
        "setEchoMode": _noop,
        "setReadOnly": _noop,
        "setRange": _noop,
        "setPrefix": _noop,
        "setDecimals": _noop,
        "setValidator": _noop,
        "setHorizontalSpacing": _noop,
        "setFieldGrowthPolicy": _noop,
        "setRowWrapPolicy": _noop,
        "setLabelAlignment": _noop,
        "setFormAlignment": _noop,
        "setRowCount": _noop,
        "setCellWidget": _noop,
        "setItem": _noop,
        "setHeaderItem": _noop,
        "setHeaderLabels": _noop,
        "setHeaderHidden": _noop,
        "setRootIsDecorated": _noop,
        "setIndentation": _noop,
        "setExpandsOnDoubleClick": _noop,
        "setSelectionMode": _noop,
        "setAlternatingRowColors": _noop,
        "setUniformRowHeights": _noop,
        "setSectionResizeMode": _noop,
        "setTabOrder": _noop,
        "setFocus": _noop,
        "setFocusPolicy": _noop,
        "setCurrentCell": _noop,
        "setCurrentItem": _noop,
        "setCurrentRow": _noop,
        "setCurrentText": _noop,
        "setCurrentPage": _noop,
        "setMinimum": _noop,
        "setMaximum": _noop,
        "setOrientation": _noop,
        "setInvertedControls": _noop,
        "setPageStep": _noop,
        "setTickPosition": _noop,
        "setCentralWidget": _noop,
        "setStatusBar": _noop,
        "setWindowFlag": _noop,
        "setWindowFlags": _noop,
        "setWindowOpacity": _noop,
        "setWindowState": _noop,
        "setAnimated": _noop,
        "setDirection": _noop,
        "setFrameShadow": _noop,
        "setLineWidth": _noop,
        "setMidLineWidth": _noop,
        "setWidgetResizable": _noop,
        "setWidget": _noop,
        "setTitle": _noop,
        "setFlat": _noop,
        "setIconSize": _noop,
        "setCursor": _noop,
        "setAttribute": _noop,
        "setContextMenuPolicy": _noop,
        "setAcceptDrops": _noop,
        "setDragDropMode": _noop,
        "setDragEnabled": _noop,
        "setAcceptRichText": _noop,
        "setLineWrapMode": _noop,
        "setLineWrapColumnOrWidth": _noop,
        "setWordWrapMode": _noop,
        "setUndoRedoEnabled": _noop,
        "setCenterOnScroll": _noop,
        "setResizeMode": _noop,
        "setIsCurrentItem": _noop,
        "setSelected": _noop,
        "setTextElideMode": _noop,
        "setResizeAnchor": _noop,
        "setRenderHint": _noop,
        "setViewport": _noop,
        "setTransformationAnchor": _noop,
        "setDragMode": _noop,
        "setCacheMode": _noop,
        "setOptimizationFlags": _noop,
        "setMouseTracking": _noop,
        "setTabPosition": _noop,
        "setTabsClosable": _noop,
        "setDocumentMode": _noop,
        "setUsesScrollButtons": _noop,
        "setDocument": _noop,
        "setUndoStack": _noop,
        "setShortcut": _noop,
        "setShortcutEnabled": _noop,
        "setAutoRepeat": _noop,
        "setAutoExclusive": _noop,
        "setAutoFillBackground": _noop,
        "setGraphicsEffect": _noop,
        "setItemDelegate": _noop,
        "setItemDelegateForColumn": _noop,
        "setItemDelegateForRow": _noop,
        "setModel": _noop,
        "setSourceModel": _noop,
        "setFilterFixedString": _noop,
        "setFilterRegExp": _noop,
        "setSortFilterProxyModel": _noop,
        "setCompleter": _noop,
        "setSortingEnabled": _noop,
        "setSelectionModel": _noop,
        "setItemSelected": _noop,
        "setCurrentScene": _noop,
        "setSceneRect": _noop,
        "setBackgroundBrush": _noop,
        "setForegroundBrush": _noop,
        "setItemIndexMethod": _noop,
        "setLayoutMode": _noop,
        "setSizeAdjustPolicy": _noop,
        "setHtml": _noop,
        "setPlainText": _noop,
        "setMarkdown": _noop,
        "setProperty": _noop,
        "setData": _noop,
        "setFlags": _noop,
        "setState": _noop,
        "setCheckState": _noop,
        "setTristate": _noop,
        "setNoChange": _noop,
        "setStyle": _noop,
        "setLocale": _noop,
        "setInputMethodHints": _noop,
        "setGraphicsItem": _noop,
        "clicked": _Signal(),
        "triggered": _Signal(),
        "toggled": _Signal(),
        "pressed": _Signal(),
        "released": _Signal(),
        "currentChanged": _Signal(),
        "currentIndexChanged": _Signal(),
        "currentTextChanged": _Signal(),
        "stateChanged": _Signal(),
        "valueChanged": _Signal(),
        "textChanged": _Signal(),
        "textEdited": _Signal(),
        "editingFinished": _Signal(),
        "returnPressed": _Signal(),
        "setVisible": _noop,
        "setParent": _noop,
        "setLayout": _noop,
        "resize": _noop,
        "sizeHint": lambda self: None,
        # QWidget window-related (used by QDialog subclasses)
        "setWindowTitle": _noop,
        "setWindowModality": _noop,
        "setSizeGripEnabled": _noop,
        # Geometry helpers for _HeightCachedLabel
        "width": lambda self: 0,
        "heightForWidth": lambda self, w: 0,
        # Visibility with tracking
        "hide": lambda self: setattr(self, "_visible", False),
        "show": lambda self: setattr(self, "_visible", True),
        "isVisible": _visible_getter,
        "update": _noop,
        "repaint": _noop,
        "close": lambda self: True,
        # Text with tracking
        "text": _text_getter,
        # Layout helpers (used by QVBoxLayout / QHBoxLayout / QFormLayout)
        "addRow": _noop,
        "insertWidget": _noop,
        "insertLayout": _noop,
    }
    return type(name, (), attrs)


def _make_qtimer_stub() -> type:
    """Build a QTimer stub that mimics the real QTimer's contract.

    The real QTimer is parented to a QObject, has setSingleShot / start
    / stop, and exposes a `timeout` signal that fires when the timer
    expires. The stub fires `timeout` synchronously inside start() —
    this matches the "0ms debounce" model that lets tests inspect
    signal payloads without spinning an event loop.
    """

    class _QTimer:
        def __init__(self, parent=None):
            self._parent = parent
            self._single_shot = False
            self._active = False
            self._interval = 0
            self.timeout = _Signal()

        def setSingleShot(self, single_shot: bool) -> None:
            self._single_shot = bool(single_shot)

        def setInterval(self, ms: int) -> None:
            self._interval = int(ms)

        def interval(self) -> int:
            return self._interval

        def start(self, ms: int = 0) -> None:
            self._active = True
            if ms:
                self._interval = int(ms)
            if self._single_shot:
                # Fire immediately so stubs behave like a 0ms debounce.
                self._active = False
                self.timeout.emit()

        def stop(self) -> None:
            self._active = False

        def isActive(self) -> bool:
            return self._active

    return _QTimer


def _make_qcoreapplication_stub() -> type:
    """Build a minimal QCoreApplication stub for tests.

    The full PySide6 classmethod contract (instance(), quit(),
    sendPostedEvents(), etc.) is not needed by Rikugan tests. Only
    ``processEvents()`` is exercised (and only as a no-op flush). The
    QTimer stub already fires synchronously on start(), so
    ``processEvents`` does not need to dispatch anything for the
    ThemeManager debounce path.
    """

    class _QCoreApplication:
        @staticmethod
        def processEvents() -> None:
            return None

    return _QCoreApplication


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
    _sentinel.WindowModality = type(
        "_WindowModality", (),
        {"NonModal": 0, "WindowModal": 1, "ApplicationModal": 2},
    )()
    _sentinel.StandardButton = type(
        "_StandardButton", (),
        {
            "NoButton": 0, "Ok": 1, "Cancel": 2, "Yes": 3, "No": 4,
            "Save": 32, "Open": 1024, "Close": 2048, "Apply": 33554432,
        },
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
            QTimer=_make_qtimer_stub(),
            # Minimal QCoreApplication stub — real tests that need a
            # real event loop should drop these stubs and re-import
            # PySide6 (see test_theme_watcher.py / test_theme_manager.py).
            # ``processEvents`` is a no-op here; the QTimer stub fires
            # synchronously on start() so the debounce in ThemeManager
            # does not need a real event loop to dispatch.
            QCoreApplication=_make_qcoreapplication_stub(),
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

    # QLineEdit needs a nested EchoMode enum (used by setEchoMode).
    _widget_stubs["QLineEdit"].EchoMode = type(
        "_LineEditEchoMode", (),
        {"Normal": 0, "NoEcho": 1, "Password": 2, "PasswordEchoOnEdit": 3},
    )()
    # QAbstractItemView SelectionMode / EditTrigger (used by QListWidget,
    # QTableWidget, QTreeWidget).
    _widget_stubs["QAbstractItemView"].SelectionMode = type(
        "_SelMode", (), {"SingleSelection": 1, "MultiSelection": 2, "ExtendedSelection": 3, "ContiguousSelection": 4, "NoSelection": 0},
    )()
    _widget_stubs["QAbstractItemView"].SelectionBehavior = type(
        "_SelBeh", (), {"SelectItems": 0, "SelectRows": 1, "SelectColumns": 2},
    )()
    _widget_stubs["QAbstractItemView"].EditTrigger = type(
        "_EditTrig", (),
        {"NoEditTriggers": 0, "CurrentChanged": 1, "DoubleClicked": 2, "SelectedClicked": 4, "EditKeyPressed": 8, "AnyKeyPressed": 16, "AllEditTriggers": 31},
    )()
    _widget_stubs["QAbstractItemView"].DragDropMode = type(
        "_DDMode", (), {"NoDragDrop": 0, "DragOnly": 1, "DropOnly": 2, "DragDrop": 3, "InternalMove": 4},
    )()
    _widget_stubs["QDialog"].DialogCode = type(
        "_DialogCode", (), {"Accepted": 1, "Rejected": 0},
    )()
    # QDialog subclasses (SettingsDialog) call self.accept() / self.reject()
    # from the Ok/Cancel button wiring.
    _widget_stubs["QDialog"].accept = lambda self: None
    _widget_stubs["QDialog"].reject = lambda self: None
    _widget_stubs["QDialog"].done = lambda self, r: None
    _widget_stubs["QDialog"].exec = lambda self: 0
    _widget_stubs["QDialog"].open = lambda self: None
    _widget_stubs["QDialogButtonBox"].StandardButton = type(
        "_DialogBoxStandardButton", (),
        {
            "NoButton": 0, "Ok": 1024, "Open": 8192, "Save": 2048, "Cancel": 4194304,
            "Close": 2097152, "Discard": 8388608, "Apply": 33554432, "Reset": 67108864,
            "RestoreDefaults": 134217728, "Help": 16777216, "SaveAll": 268435456,
            "Yes": 16384, "YesToAll": 32768, "No": 65536, "NoToAll": 131072,
            "Abort": 262144, "Retry": 524288, "Ignore": 1048576,
        },
    )()
    # QDialogButtonBox needs accepted/rejected/clicked signals for the
    # Ok/Cancel wiring in SettingsDialog.
    _widget_stubs["QDialogButtonBox"].accepted = _Signal()
    _widget_stubs["QDialogButtonBox"].rejected = _Signal()
    _widget_stubs["QDialogButtonBox"].clicked = _Signal()
    _widget_stubs["QFrame"].Shape = type(
        "_FrameShape", (),
        {"NoFrame": 0, "Box": 1, "Panel": 2, "StyledPanel": 6, "HLine": 4, "VLine": 5, "WinPanel": 3},
    )()
    _widget_stubs["QFrame"].Shadow = type(
        "_FrameShadow", (), {"Plain": 16, "Raised": 32, "Sunken": 48},
    )()

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

    # QApplication needs a small state-tracking stub so that
    # QApplication.primaryScreen() and screen.availableGeometry() return
    # a usable geometry in tests. The real QApplication is a singleton
    # managed by Qt; the stub keeps the same staticmethod contract so
    # code like ``QApplication.primaryScreen()`` works without an event
    # loop. ``processEvents`` and ``setStyleSheet`` are no-ops so the
    # ThemeManager's QSS-rebuild path is silent in tests.
    def _qapp_primary_screen():
        return _qapp_screen_stub

    def _qapp_screen_geometry():
        class _Geom:
            def __init__(self, w: int, h: int) -> None:
                self._w = w
                self._h = h

            def width(self) -> int:
                return self._w

            def height(self) -> int:
                return self._h

        return _Geom(1920, 1080)

    class _QAppScreen:
        def availableGeometry(self):
            return _qapp_screen_geometry()

    _qapp_screen_stub = _QAppScreen()

    def _make_qapplication_stub() -> type:
        class _QApplication:
            @staticmethod
            def instance():
                return _qapp_singleton

            @staticmethod
            def primaryScreen():
                return _qapp_screen_stub

            def __init__(self, *a, **k):
                pass

            def setStyleSheet(self, qss: str) -> None:
                # Track so tests can assert that _apply_now does not
                # clobber the host's stylesheet.
                _qapp_singleton._stylesheet = qss

            def styleSheet(self) -> str:
                return getattr(_qapp_singleton, "_stylesheet", "")

            def processEvents(self) -> None:
                return None

        _qapp_singleton = _QApplication()
        return _QApplication

    sys.modules["PySide6.QtWidgets"].QApplication = _make_qapplication_stub()

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

    # QPainter is a no-op stub for tests. paintEvent() methods can call
    # ``p = QPainter(self); ...; p.end()`` without crashing in the test
    # environment. The ThemePreviewChip's paintEvent exercises the full
    # QPainter surface (fillRect, setPen, drawText, end) — the stub
    # absorbs all of these as no-ops.
    def _qpainter_init(self, *a, **k):
        return None

    def _qpainter_end(self):
        return None

    def _qpainter_noop(self, *a, **k):
        return None

    _qpainter = type(
        "QPainter",
        (),
        {
            "__init__": _qpainter_init,
            "end": _qpainter_end,
            "fillRect": _qpainter_noop,
            "setPen": _qpainter_noop,
            "drawText": _qpainter_noop,
        },
    )
    sys.modules["PySide6.QtGui"].QPainter = _qpainter

    # QTabWidget and QComboBox need state-tracking stubs so the
    # Appearance tab tests can verify addTab/count/tabText/addItem/itemData
    # and that setCurrentIndex fires currentIndexChanged synchronously
    # (matching the real Qt behavior in single-threaded test mode).
    def _make_qtabwidget_stub() -> type:
        class _QTabWidget:
            def __init__(self, parent=None):
                self._tabs: list = []  # list of (label, widget, data)
                self._current = 0
                self.currentChanged = _Signal()
                self.currentIndexChanged = _Signal()

            def addTab(self, widget, label):
                idx = len(self._tabs)
                self._tabs.append((label, widget, None))
                return idx

            def insertTab(self, index, widget, label):
                # Clamp to [0, len] like real Qt.
                index = max(0, min(index, len(self._tabs)))
                self._tabs.insert(index, (label, widget, None))
                return index

            def count(self):
                return len(self._tabs)

            def tabText(self, idx):
                if 0 <= idx < len(self._tabs):
                    return self._tabs[idx][0]
                return ""

            def widget(self, idx):
                if 0 <= idx < len(self._tabs):
                    return self._tabs[idx][1]
                return None

            def currentIndex(self):
                return self._current

            def setCurrentIndex(self, idx):
                if idx == self._current:
                    return
                self._current = idx
                self.currentChanged.emit(idx)
                self.currentIndexChanged.emit(idx)

        return _QTabWidget

    def _make_qcombobox_stub() -> type:
        class _QComboBox:
            def __init__(self, parent=None):
                self._items: list = []  # list of (label, data)
                self._current = -1
                self._editable = False
                self._text = ""
                self._blocked = 0
                self.currentIndexChanged = _Signal()
                self.currentTextChanged = _Signal()
                self.activated = _Signal()
                self.highlighted = _Signal()

            def addItem(self, label, data=None):
                self._items.append((label, data))

            def addItems(self, labels):
                for label in labels:
                    self.addItem(label)

            def count(self):
                return len(self._items)

            def itemData(self, idx):
                if 0 <= idx < len(self._items):
                    return self._items[idx][1]
                return None

            def itemText(self, idx):
                if 0 <= idx < len(self._items):
                    return self._items[idx][0]
                return ""

            def currentIndex(self):
                return self._current

            def setCurrentIndex(self, idx):
                if idx == self._current:
                    return
                if not (0 <= idx < len(self._items)):
                    return
                self._current = idx
                if not self._blocked:
                    self.currentIndexChanged.emit(idx)
                    self.currentTextChanged.emit(self._items[idx][0])

            def currentText(self):
                if 0 <= self._current < len(self._items):
                    return self._items[self._current][0]
                return ""

            def setCurrentText(self, text):
                for i, (label, _data) in enumerate(self._items):
                    if label == text:
                        self.setCurrentIndex(i)
                        return

            def findText(self, text):
                for i, (label, _data) in enumerate(self._items):
                    if label == text:
                        return i
                return -1

            def findData(self, data):
                for i, (_label, d) in enumerate(self._items):
                    if d == data:
                        return i
                return -1

            def setEditable(self, editable):
                self._editable = bool(editable)

            def setMinimumWidth(self, w):
                return None

            def setFixedWidth(self, w):
                return None

            def setMaximumWidth(self, w):
                return None

            def setSizeAdjustPolicy(self, p):
                return None

            def view(self):
                return None

            def model(self):
                return None

            def blockSignals(self, block):
                if block:
                    self._blocked += 1
                else:
                    self._blocked = max(0, self._blocked - 1)
                return True

            def clear(self):
                self._items.clear()
                self._current = -1

        return _QComboBox

    sys.modules["PySide6.QtWidgets"].QTabWidget = _make_qtabwidget_stub()
    sys.modules["PySide6.QtWidgets"].QComboBox = _make_qcombobox_stub()
