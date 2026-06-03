"""Theme helpers and dark-theme stylesheet for Rikugan UI."""

from __future__ import annotations

from ..core.host import is_ida

_FALLBACK_COLORS = {
    "window": "#1e1e1e",
    "window_text": "#d4d4d4",
    "base": "#252526",
    "alt_base": "#2d2d2d",
    "text": "#d4d4d4",
    "button": "#2d2d2d",
    "button_text": "#d4d4d4",
    "highlight": "#569cd6",
    "highlight_text": "#ffffff",
    "mid": "#808080",
    "dark": "#1a1a1a",
    "light": "#f3f3f3",
}


def _hex_luminance(color: str) -> float:
    color = color.lstrip("#")
    if len(color) != 6:
        return 0.0
    r = int(color[0:2], 16) / 255.0
    g = int(color[2:4], 16) / 255.0
    b = int(color[4:6], 16) / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _blend_channel(a: int, b: int, amount: float) -> int:
    amount = max(0.0, min(1.0, amount))
    return round(a + (b - a) * amount)


def blend_theme_color(color_a: str, color_b: str, amount: float) -> str:
    """Blend two ``#rrggbb`` colors."""
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    if len(a) != 6 or len(b) != 6:
        return color_a

    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return (
        f"#{_blend_channel(ar, br, amount):02x}{_blend_channel(ag, bg, amount):02x}{_blend_channel(ab, bb, amount):02x}"
    )


def _normalize_ida_palette(colors: dict[str, str]) -> dict[str, str]:
    """Derive control surfaces from IDA's dock background instead of native widget roles."""
    window = colors["window"]
    window_text = colors["window_text"]
    is_dark = _hex_luminance(window) < 0.5
    toward = "#ffffff" if is_dark else "#000000"
    surface = blend_theme_color(window, toward, 0.08 if is_dark else 0.035)
    alt_surface = blend_theme_color(window, toward, 0.14 if is_dark else 0.07)
    mid = blend_theme_color(window, toward, 0.22 if is_dark else 0.16)
    colors = dict(colors)
    colors["base"] = surface
    colors["button"] = surface
    colors["alt_base"] = alt_surface
    colors["text"] = window_text
    colors["button_text"] = window_text
    colors["mid"] = mid
    colors["dark"] = blend_theme_color(window, "#000000", 0.20 if is_dark else 0.08)
    colors["light"] = blend_theme_color(window, "#ffffff", 0.14 if is_dark else 0.20)
    return colors


def _palette_role(qpalette, role_name: str):
    """Return a Qt palette role compatible with Qt5/Qt6 enum layouts."""
    role = getattr(qpalette, role_name, None)
    if role is not None:
        return role
    color_role = getattr(qpalette, "ColorRole", None)
    if color_role is not None:
        return getattr(color_role, role_name)
    raise AttributeError(role_name)


def get_host_palette_colors(source=None) -> dict[str, str]:
    """Return the current Qt palette colors, with stable fallbacks."""
    try:
        from .qt_compat import QApplication, QPalette
    except ImportError:
        return dict(_FALLBACK_COLORS)

    try:
        palette = None
        if source is not None and hasattr(source, "palette"):
            palette = source.palette()
        if palette is None:
            instance = getattr(QApplication, "instance", None)
            app = instance() if callable(instance) else None
            if app is None or not hasattr(app, "palette"):
                return dict(_FALLBACK_COLORS)
            palette = app.palette()
        colors = {
            "window": palette.color(_palette_role(QPalette, "Window")).name(),
            "window_text": palette.color(_palette_role(QPalette, "WindowText")).name(),
            "base": palette.color(_palette_role(QPalette, "Base")).name(),
            "alt_base": palette.color(_palette_role(QPalette, "AlternateBase")).name(),
            "text": palette.color(_palette_role(QPalette, "Text")).name(),
            "button": palette.color(_palette_role(QPalette, "Button")).name(),
            "button_text": palette.color(_palette_role(QPalette, "ButtonText")).name(),
            "highlight": palette.color(_palette_role(QPalette, "Highlight")).name(),
            "highlight_text": palette.color(_palette_role(QPalette, "HighlightedText")).name(),
            "mid": palette.color(_palette_role(QPalette, "Mid")).name(),
            "dark": palette.color(_palette_role(QPalette, "Dark")).name(),
            "light": palette.color(_palette_role(QPalette, "Light")).name(),
        }
        if use_native_host_theme():
            colors = _normalize_ida_palette(colors)
        return colors
    except Exception:
        return dict(_FALLBACK_COLORS)


def use_native_host_theme() -> bool:
    """Return True when the host should keep its own native theme.

    IDA owns the overall dock styling, but Rikugan still derives local
    widget surfaces from the live host colors so the chat remains readable
    in both light and dark themes.
    """
    return is_ida()


def maybe_host_stylesheet(css: str) -> str:
    """Return the stylesheet unless the host should keep its native theme."""
    return "" if use_native_host_theme() else css


def host_stylesheet(custom_css: str, native_css: str = "") -> str:
    """Return the stylesheet for the active host theme mode."""
    return native_css if use_native_host_theme() else custom_css


def build_theme_stylesheet(source=None) -> str:
    """Return the active panel stylesheet for the current host."""
    if use_native_host_theme():
        return IDA_NATIVE_THEME
    return DARK_THEME


def build_small_button_stylesheet(source=None, danger: bool = False) -> str:
    """Return a palette-aware small button stylesheet for host UIs."""
    if use_native_host_theme() and not danger:
        return ""
    if use_native_host_theme() and danger:
        # In native theme, only override colors — keep native sizing/layout
        return (
            "QPushButton { color: #c42b1c; border: 1px solid #c42b1c; }"
            "QPushButton:hover { background: #3a1a1a; }"
        )
    colors = get_host_palette_colors(source)
    bg = colors["button"]
    fg = colors["button_text"]
    border = blend_theme_color(colors["mid"], colors["window"], 0.35)
    hover = blend_theme_color(bg, colors["light"], 0.12)
    pressed = blend_theme_color(bg, colors["dark"], 0.12)
    if danger:
        fg = "#f87171"
        border = blend_theme_color("#f44747", colors["window"], 0.2)
        hover = blend_theme_color("#3a1a1a", colors["light"], 0.12)
    return (
        f"QPushButton {{ background-color: {bg}; color: {fg}; border: 1px solid {border}; "
        f"border-radius: 6px; padding: 4px; font-size: 11px; }}"
        f"QPushButton:hover {{ background-color: {hover}; }}"
        f"QPushButton:pressed {{ background-color: {pressed}; }}"
        f"QPushButton:disabled {{ color: {blend_theme_color(fg, colors['window'], 0.45)}; "
        f"border-color: {blend_theme_color(border, colors['window'], 0.35)}; }}"
    )


def build_input_area_stylesheet(source=None) -> str:
    """Return a palette-aware input editor stylesheet."""
    if use_native_host_theme():
        return ""
    colors = get_host_palette_colors(source)
    bg = blend_theme_color(colors["window"], colors["button"], 0.22)
    text = colors["window_text"]
    border = blend_theme_color(colors["mid"], colors["window"], 0.35)
    return (
        "QPlainTextEdit#input_area { "
        f"background-color: {bg}; color: {text}; "
        f"border: 1px solid {border}; border-radius: 8px; "
        "padding: 8px; font-size: 13px; "
        f"selection-background-color: {colors['highlight']}; "
        f"selection-color: {colors['highlight_text']}; }}"
        f"QPlainTextEdit#input_area:focus {{ border-color: {colors['highlight']}; }}"
    )


IDA_NATIVE_THEME = """
QWidget#rikugan_panel {
    background: transparent;
}

QScrollArea#chat_scroll {
    border: none;
    background: transparent;
}

QWidget#chat_container {
    background: transparent;
}

QToolButton#collapse_button {
    border: none;
    background: transparent;
    padding: 0px;
}

QLabel#tool_content {
    font-family: Consolas, "Courier New", monospace;
    font-size: 10px;
}
"""


DARK_THEME = """
QWidget#rikugan_panel {
    background-color: #1e1e1e;
    color: #d4d4d4;
}

QScrollArea#chat_scroll {
    background-color: #1e1e1e;
    border: none;
}

QWidget#chat_container {
    background-color: #1e1e1e;
}

QFrame#message_user {
    background-color: #2d2d2d;
    border-radius: 8px;
    padding: 8px;
    margin: 4px 8px 4px 8px;
}

QFrame#message_assistant {
    background-color: #1e1e1e;
    border-radius: 8px;
    padding: 8px;
    margin: 4px 8px 4px 8px;
}

QFrame#message_tool {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#message_thinking {
    background-color: #1e1e1e;
    border-radius: 6px;
    padding: 4px 8px;
    margin: 2px 8px;
}

QLabel#tool_header {
    color: #569cd6;
    font-weight: bold;
    font-size: 11px;
}

QLabel#tool_content {
    color: #9cdcfe;
    font-family: monospace;
    font-size: 11px;
}

QPlainTextEdit#input_area {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 8px;
    font-size: 13px;
    selection-background-color: #264f78;
}

QPlainTextEdit#input_area:focus {
    border-color: #007acc;
}

QPushButton#send_button {
    background-color: #007acc;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}

QPushButton#send_button:hover {
    background-color: #1a8ad4;
}

QPushButton#send_button:pressed {
    background-color: #005a9e;
}

QPushButton#send_button:disabled {
    background-color: #3c3c3c;
    color: #6c6c6c;
}

QPushButton#cancel_button {
    background-color: #c72e2e;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}

QFrame#context_bar {
    background-color: #252526;
    border-top: 1px solid #3c3c3c;
    padding: 4px 8px;
}

QLabel#context_label {
    color: #808080;
    font-size: 11px;
}

QLabel#context_value {
    color: #cccccc;
    font-size: 11px;
}

QFrame#plan_step {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}

QFrame#plan_step_active {
    background-color: #252526;
    border: 1px solid #007acc;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}

QFrame#plan_step_done {
    background-color: #252526;
    border: 1px solid #4ec9b0;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}

QToolButton#collapse_button {
    border: none;
    color: #808080;
    font-size: 10px;
}

QToolButton#collapse_button:hover {
    color: #d4d4d4;
}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px;
}

QGroupBox {
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}

QFrame#tools_panel {
    background-color: #1e1e1e;
    border-left: 1px solid #3c3c3c;
}

QFrame#tools_panel QTabWidget::pane {
    border: none;
}

QFrame#tools_panel QTabBar {
    background: #1e1e1e;
    border: none;
}

QFrame#tools_panel QTabBar::tab {
    background: #252526;
    color: #cccccc;
    padding: 4px 12px;
    border: none;
    border-right: 1px solid #3c3c3c;
    font-size: 11px;
}

QFrame#tools_panel QTabBar::tab:selected {
    background: #1e1e1e;
    color: #ffffff;
}

QFrame#tools_panel QTabBar::tab:hover {
    background: #2d2d2d;
}

QTreeWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    font-size: 11px;
}

QTreeWidget::item {
    padding: 2px 4px;
}

QTreeWidget::item:selected {
    background-color: #264f78;
}

QTreeWidget::item:hover {
    background-color: #2d2d2d;
}

QHeaderView::section {
    background-color: #252526;
    color: #cccccc;
    border: none;
    border-right: 1px solid #3c3c3c;
    padding: 3px 6px;
    font-size: 11px;
}

QTableWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    gridline-color: #3c3c3c;
    font-size: 11px;
}

QTableWidget::item {
    padding: 2px 4px;
}

QTableWidget::item:selected {
    background-color: #264f78;
}

QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    text-align: center;
    color: #d4d4d4;
    font-size: 10px;
    height: 14px;
}

QProgressBar::chunk {
    background-color: #4ec9b0;
    border-radius: 2px;
}

QRadioButton {
    color: #d4d4d4;
    font-size: 11px;
    spacing: 4px;
}

QTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    font-size: 11px;
}
"""
