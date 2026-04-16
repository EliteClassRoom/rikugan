"""IDA PluginForm wrapper around the shared Rikugan panel core.

This module provides IDA Pro theme integration, automatically detecting
the current color scheme (dark/light) and applying appropriate styling.
"""

from __future__ import annotations

import importlib
from typing import Any

from rikugan.ui.panel_core import RikuganPanelCore
from rikugan.ui.qt_compat import QT_BINDING, QVBoxLayout, QWidget

from .actions import RikuganUIHooks
from .session_controller import IdaSessionController
from .tools_form import RikuganToolsForm

idaapi = importlib.import_module("idaapi")
ida_kernwin = importlib.import_module("ida_kernwin")


def _get_ida_theme_colors() -> dict[str, tuple[int, int, int]]:
    """Extract current IDA Pro theme colors.

    Returns a dictionary of color names to RGB tuples based on IDA's
    current color scheme. This allows Rikugan to blend in with IDA's UI.
    """
    colors = {}

    # Try to get colors from IDA's kernel window API
    # Note: ida_kernwin.get_widget_color() returns IDA's internal widget colors,
    # NOT the custom Qt CSS theme colors the user has configured.
    # When it returns near-black values like (30,30,30) it's IDA's built-in fallback
    # for custom themes. We detect this and use Monokai-inspired light fallbacks.
    try:
        bg_raw = _ida_color_to_rgb(ida_kernwin.get_widget_color(ida_kernwin.BCKCOLOR))
        bg_brightness = (bg_raw[0] * 299 + bg_raw[1] * 587 + bg_raw[2] * 114) / 1000
        # If API returned IDA's internal dark fallback (brightness < 20), treat as "unknown"
        if bg_brightness < 20:
            colors["background"] = (245, 240, 232)  # Monokai Light paper
            colors["text"] = (44, 44, 44)
        else:
            colors["background"] = bg_raw
            try:
                colors["text"] = _ida_color_to_rgb(ida_kernwin.get_widget_color(ida_kernwin.FGCOLOR))
            except Exception:
                colors["text"] = (44, 44, 44)
    except Exception:
        # API completely unavailable — use Monokai Light fallbacks
        colors["background"] = (245, 240, 232)  # Monokai Light paper
        colors["text"] = (44, 44, 44)

    # Calculate derived colors based on background brightness
    bg = colors["background"]
    bg_brightness = (bg[0] * 299 + bg[1] * 587 + bg[2] * 114) / 1000
    is_dark = bg_brightness < 128

    if is_dark:
        # Dark theme derived colors
        colors["surface"] = _lighten_color(bg, 15)
        colors["surface_variant"] = _lighten_color(bg, 25)
        colors["border"] = _lighten_color(bg, 35)
        colors["text_secondary"] = _blend_colors(colors["text"], bg, 0.6)
        colors["accent"] = (0, 122, 204)  # IDA's blue accent
        colors["accent_hover"] = (26, 138, 212)
        colors["selection"] = (38, 79, 120)
        colors["success"] = (78, 201, 176)
        colors["error"] = (199, 46, 46)
        colors["tool_header"] = (86, 156, 214)
        colors["tool_content"] = (156, 220, 254)
        # Code block: slightly darker than surface for contrast
        colors["code_block_bg"] = _lighten_color(bg, 5)
        colors["code_block_border"] = _lighten_color(bg, 20)
        colors["code_text"] = colors["text"]
    else:
        # Light theme derived colors
        colors["surface"] = _darken_color(bg, 10)
        colors["surface_variant"] = _darken_color(bg, 20)
        colors["border"] = _darken_color(bg, 30)
        colors["text_secondary"] = _blend_colors(colors["text"], bg, 0.6)
        colors["accent"] = (0, 102, 204)  # Darker blue for light theme
        colors["accent_hover"] = (0, 122, 224)
        colors["selection"] = (180, 210, 240)
        colors["success"] = (0, 128, 100)
        colors["error"] = (180, 50, 50)
        colors["tool_header"] = (0, 80, 160)
        colors["tool_content"] = (0, 100, 180)
        # Code block: warm gray, distinct from message background
        colors["code_block_bg"] = _darken_color(bg, 8)  # slightly darker warm surface
        colors["code_block_border"] = _darken_color(bg, 20)
        colors["code_text"] = colors["text"]

    return colors


def _ida_color_to_rgb(color_val: int) -> tuple[int, int, int]:
    """Convert IDA color value to RGB tuple.

    IDA stores colors as 0xBBGGRR (blue, green, red).
    """
    if color_val == 0xFFFFFFFF:  # Default/invalid color
        return (30, 30, 30)

    r = color_val & 0xFF
    g = (color_val >> 8) & 0xFF
    b = (color_val >> 16) & 0xFF
    return (r, g, b)


def _lighten_color(rgb: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    """Lighten an RGB color by a percentage amount."""
    r, g, b = rgb
    factor = 1 + (amount / 100)
    return (min(255, int(r * factor)), min(255, int(g * factor)), min(255, int(b * factor)))


def _darken_color(rgb: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    """Darken an RGB color by a percentage amount."""
    r, g, b = rgb
    factor = 1 - (amount / 100)
    return (max(0, int(r * factor)), max(0, int(g * factor)), max(0, int(b * factor)))


def _blend_colors(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    """Blend two colors with the given alpha (0-1)."""
    return (
        int(rgb1[0] * alpha + rgb2[0] * (1 - alpha)),
        int(rgb1[1] * alpha + rgb2[1] * (1 - alpha)),
        int(rgb1[2] * alpha + rgb2[2] * (1 - alpha)),
    )


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def generate_ida_theme_stylesheet() -> str:
    """Generate a Qt stylesheet that matches IDA Pro's current theme.

    This function detects IDA's color scheme and generates appropriate
    styling for all Rikugan UI components.
    """
    c = _get_ida_theme_colors()

    # Convert all colors to hex
    bg = _rgb_to_hex(c["background"])
    surface = _rgb_to_hex(c["surface"])
    surface_variant = _rgb_to_hex(c["surface_variant"])
    border = _rgb_to_hex(c["border"])
    text = _rgb_to_hex(c["text"])
    text_secondary = _rgb_to_hex(c["text_secondary"])
    accent = _rgb_to_hex(c["accent"])
    accent_hover = _rgb_to_hex(c["accent_hover"])
    selection = _rgb_to_hex(c["selection"])
    success = _rgb_to_hex(c["success"])
    error = _rgb_to_hex(c["error"])
    tool_header = _rgb_to_hex(c["tool_header"])
    tool_content = _rgb_to_hex(c["tool_content"])
    code_block_bg = _rgb_to_hex(c["code_block_bg"])
    code_block_border = _rgb_to_hex(c["code_block_border"])
    code_text = _rgb_to_hex(c["code_text"])

    # Determine if dark theme for specific adjustments
    bg_brightness = (c["background"][0] * 299 + c["background"][1] * 587 + c["background"][2] * 114) / 1000
    is_dark = bg_brightness < 128

    disabled_bg = _rgb_to_hex(_blend_colors(c["surface"], c["background"], 0.5))
    disabled_text = _rgb_to_hex(_blend_colors(c["text"], c["background"], 0.3))

    return f"""
QWidget#rikugan_panel {{
    background-color: {bg};
    color: {text};
}}

QScrollArea#chat_scroll {{
    background-color: {bg};
    border: none;
}}

QWidget#chat_container {{
    background-color: {bg};
}}

QFrame#message_user {{
    background-color: {surface};
    border-radius: 8px;
    padding: 8px;
    margin: 4px 8px 4px 8px;
}}

QFrame#message_assistant {{
    background-color: {bg};
    border-radius: 8px;
    padding: 8px;
    margin: 4px 8px 4px 8px;
}}

QFrame#message_tool {{
    background-color: {surface_variant};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}}

QFrame#message_thinking {{
    background-color: {bg};
    border-radius: 6px;
    padding: 4px 8px;
    margin: 2px 8px;
}}

QLabel#tool_header {{
    color: {tool_header};
    font-weight: bold;
    font-size: 11px;
}}

QLabel#tool_content {{
    color: {tool_content};
    font-family: monospace;
    font-size: 11px;
}}

QPlainTextEdit#input_area {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 8px;
    font-size: 13px;
    selection-background-color: {selection};
}}

QPlainTextEdit#input_area:focus {{
    border-color: {accent};
}}

QPushButton#send_button {{
    background-color: {accent};
    color: {"white" if is_dark else "white"};
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}}

QPushButton#send_button:hover {{
    background-color: {accent_hover};
}}

QPushButton#send_button:pressed {{
    background-color: {_rgb_to_hex(_darken_color(c["accent"], 20))};
}}

QPushButton#send_button:disabled {{
    background-color: {disabled_bg};
    color: {disabled_text};
}}

QPushButton#cancel_button {{
    background-color: {error};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}}

QFrame#context_bar {{
    background-color: {surface_variant};
    border-top: 1px solid {border};
    padding: 4px 8px;
}}

QLabel#context_label {{
    color: {text_secondary};
    font-size: 11px;
}}

QLabel#context_value {{
    color: {text};
    font-size: 11px;
}}

QFrame#plan_step {{
    background-color: {surface_variant};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}}

QFrame#plan_step_active {{
    background-color: {surface_variant};
    border: 1px solid {accent};
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}}

QFrame#plan_step_done {{
    background-color: {surface_variant};
    border: 1px solid {success};
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}}

QToolButton#collapse_button {{
    border: none;
    color: {text_secondary};
    font-size: 10px;
}}

QToolButton#collapse_button:hover {{
    color: {text};
}}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px;
}}

QGroupBox {{
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

QFrame#tools_panel {{
    background-color: {bg};
    border-left: 1px solid {border};
}}

QFrame#tools_panel QTabWidget::pane {{
    border: none;
}}

QFrame#tools_panel QTabBar {{
    background: {bg};
    border: none;
}}

QFrame#tools_panel QTabBar::tab {{
    background: {surface_variant};
    color: {text};
    padding: 4px 12px;
    border: none;
    border-right: 1px solid {border};
    font-size: 11px;
}}

QFrame#tools_panel QTabBar::tab:selected {{
    background: {bg};
    color: {text};
}}

QFrame#tools_panel QTabBar::tab:hover {{
    background: {surface};
}}

QTreeWidget {{
    background-color: {bg};
    color: {text};
    border: none;
    font-size: 11px;
}}

QTreeWidget::item {{
    padding: 2px 4px;
}}

QTreeWidget::item:selected {{
    background-color: {selection};
}}

QTreeWidget::item:hover {{
    background-color: {surface};
}}

QHeaderView::section {{
    background-color: {surface_variant};
    color: {text};
    border: none;
    border-right: 1px solid {border};
    padding: 3px 6px;
    font-size: 11px;
}}

QTableWidget {{
    background-color: {bg};
    color: {text};
    border: none;
    gridline-color: {border};
    font-size: 11px;
}}

QTableWidget::item {{
    padding: 2px 4px;
}}

QTableWidget::item:selected {{
    background-color: {selection};
}}

QProgressBar {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 3px;
    text-align: center;
    color: {text};
    font-size: 10px;
    height: 14px;
}}

QProgressBar::chunk {{
    background-color: {success};
    border-radius: 2px;
}}

QRadioButton {{
    color: {text};
    font-size: 11px;
    spacing: 4px;
}}

QTextEdit {{
    background-color: {bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    font-size: 11px;
}}

QTabBar {{ 
    background: {surface};
    border: none;
    border-bottom: 1px solid {border};
}}

QTabBar::tab {{ 
    background: {surface};
    color: {text_secondary};
    padding: 4px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 11px;
}}

QTabBar::tab:selected {{ 
    color: {text};
    border-bottom: 2px solid {success};
}}

QTabBar::tab:hover:!selected {{ 
    color: {text};
}}

QToolButton {{
    color: {text};
    border: none;
    background: transparent;
}}

QToolButton:hover {{
    background: {surface};
    border-radius: 3px;
}}

QMenu {{
    background-color: {surface_variant};
    color: {text};
    border: 1px solid {border};
}}

QMenu::item:selected {{
    background-color: {selection};
}}

QMessageBox {{
    background-color: {bg};
}}

QDialog {{
    background-color: {bg};
}}

QDialogButtonBox {{
    background-color: {bg};
}}

/* Message widgets */
QFrame#thinking_block {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 6px;
}}

QFrame#message_queued {{
    border: 1px dashed {accent};
    border-radius: 6px;
    background-color: {bg};
}}

QFrame#message_question {{
    border: 1px solid {tool_header};
    border-radius: 6px;
    background-color: {surface};
}}

QLabel#msg_role_label {{
    color: {success};
    font-weight: bold;
    font-size: 11px;
}}

QLabel#collapse_button {{
    border: none;
    color: {text_secondary};
    font-size: 10px;
}}

QLabel#thinking_header {{
    color: {text_secondary};
    font-size: 11px;
    font-style: italic;
}}

QLabel#thinking_content {{
    color: {text_secondary};
    font-size: 12px;
}}

QLabel#star_label {{
    color: {tool_header};
    font-size: 14px;
}}

QLabel#phrase_label {{
    color: {text_secondary};
    font-style: italic;
    font-size: 12px;
}}

QLabel#queued_badge {{
    color: {text_secondary};
    font-size: 10px;
    font-style: italic;
}}

QLabel#question_header {{
    color: {tool_header};
    font-weight: bold;
    font-size: 11px;
}}

QLabel#question_content {{
    color: {text};
    font-size: 13px;
}}

QLabel#phase_label {{
    color: {tool_header};
    font-weight: bold;
    font-size: 11px;
}}

QLabel#reason_label {{
    color: {text_secondary};
    font-size: 11px;
}}

QLabel#cat_label {{
    font-weight: bold;
    font-size: 10px;
}}

QLabel#addr_label {{
    color: {text_secondary};
    font-family: monospace;
    font-size: 10px;
}}

QLabel#finding_summary {{
    color: {text};
    font-size: 11px;
}}

QLabel#note_title {{
    font-weight: bold;
    font-size: 11px;
}}

QLabel#note_genre {{
    color: {text_secondary};
    font-size: 10px;
    font-style: italic;
}}

QLabel#note_path {{
    color: {text_secondary};
    font-family: monospace;
    font-size: 10px;
}}

QLabel#note_preview {{
    color: {text_secondary};
    font-size: 11px;
}}

QLabel#subagent_icon {{
    font-size: 14px;
}}

QLabel#subagent_label {{
    font-weight: bold;
    font-size: 11px;
}}

QLabel#subagent_detail {{
    color: {text_secondary};
    font-size: 11px;
}}

QLabel#error_header {{
    color: {error};
    font-weight: bold;
    font-size: 11px;
}}

QLabel#error_content {{
    color: {text};
    font-size: 12px;
}}

QLabel#msg_content {{
    color: {text};
    font-size: 13px;
}}

QLabel#relevance_star {{
    color: {tool_header};
    font-size: 12px;
}}

QFrame#finding_tool, QFrame#note_tool, QFrame#subagent_tool {{
    border: 1px solid {border};
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}}

QFrame#skill_popup {{
    border: 1px solid {border};
    border-radius: 4px;
    padding: 2px;
}}

QFrame#skill_popup QLabel {{
    padding: 3px 8px;
}}

QFrame#skill_popup QLabel[selected="true"] {{
    background-color: {selection};
    border-radius: 3px;
}}

QPushButton#option_btn {{
    background-color: {accent};
    color: white;
    border: 1px solid {accent_hover};
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 12px;
}}

QPushButton#option_btn:hover {{
    background-color: {accent_hover};
}}

QPushButton#option_btn:pressed {{
    background-color: {_rgb_to_hex(_darken_color(c["accent"], 20))};
}}

QPushButton#option_btn:disabled {{
    color: {text_secondary};
    background-color: {surface};
    border-color: {border};
}}
"""


class RikuganPanel(idaapi.PluginForm):
    """IDA dockable form embedding the shared panel core widget.

    This panel automatically adapts to IDA Pro's current color theme,
    ensuring visual consistency with the rest of the IDA interface.
    """

    def __init__(self):
        super().__init__()
        self._form_widget: QWidget | None = None
        self._root: QWidget | None = None
        self._core: RikuganPanelCore | None = None

    def OnCreate(self, form: Any) -> None:
        if QT_BINDING == "PyQt5":
            self._form_widget = self.FormToPyQtWidget(form)
        else:
            try:
                self._form_widget = self.FormToPySideWidget(form)
            except Exception:
                self._form_widget = self.FormToPyQtWidget(form)

        self._root = QWidget()
        form_layout = QVBoxLayout(self._form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addWidget(self._root)

        root_layout = QVBoxLayout(self._root)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # Create the core panel
        self._core = RikuganPanelCore(
            controller_factory=IdaSessionController,
            ui_hooks_factory=lambda panel_getter: RikuganUIHooks(panel_getter=panel_getter),
            tools_form_factory=lambda tools_widget: RikuganToolsForm(tools_widget),
            parent=self._root,
        )
        root_layout.addWidget(self._core)

        # Apply IDA theme-aware stylesheet
        self._apply_ida_theme()

    def _apply_ida_theme(self) -> None:
        """Apply the IDA Pro theme-aware stylesheet to the panel.

        This method respects the config's theme setting. If theme is "dark"
        or "light", use the predefined stylesheets. If "ida" (default),
        apply a minimal targeted stylesheet for Rikugan-specific elements while
        inheriting IDA's Qt stylesheet for everything else.
        """
        from rikugan.ui.markdown import clear_code_block_theme, set_code_block_theme

        config_theme = getattr(self._core, "_config", None)
        if config_theme is not None:
            config_theme = config_theme.theme

        if config_theme == "dark":
            self._core.set_theme("dark")
            clear_code_block_theme()
            return
        elif config_theme == "light":
            self._core.set_theme("light")
            clear_code_block_theme()
            return

        # config_theme == "ida" or invalid — apply minimal targeted overrides.
        # We call set_theme("ida") to disable dark markdown colors, and set
        # explicit code block colors so code blocks have distinct backgrounds.
        # We also apply a minimal stylesheet for Rikugan's custom widgets that
        # need visual distinction (thinking block, queued messages, etc.)
        self._core.set_theme("ida")
        c = _get_ida_theme_colors()
        set_code_block_theme(
            bg=_rgb_to_hex(c["code_block_bg"]),
            border=_rgb_to_hex(c["code_block_border"]),
            text=_rgb_to_hex(c["code_text"]),
        )

        # Apply a minimal targeted stylesheet — only Rikugan's custom widgets.
        # Everything else inherits IDA's Qt stylesheet.
        bg = _rgb_to_hex(c["background"])
        surface = _rgb_to_hex(c["surface"])
        surface_variant = _rgb_to_hex(c["surface_variant"])
        border = _rgb_to_hex(c["border"])
        text_secondary = _rgb_to_hex(c["text_secondary"])
        accent = _rgb_to_hex(c["accent"])
        code_block_bg = _rgb_to_hex(c["code_block_bg"])
        code_text = _rgb_to_hex(c["code_text"])

        minimal_style = f"""
        QFrame#thinking_block {{
            background-color: {surface};
            border-left: 3px dashed {accent};
            border-top: 1px solid {border};
            border-right: 1px solid {border};
            border-bottom: 1px solid {border};
            border-radius: 4px;
        }}
        QFrame#message_queued {{
            border: 1px dashed {accent};
            border-radius: 6px;
            background-color: {surface};
        }}
        QFrame#message_question {{
            border: 1px solid {accent};
            border-radius: 6px;
            background-color: {surface_variant};
        }}
        """
        self._core.setStyleSheet(minimal_style)

    def OnClose(self, form):
        self.shutdown()
        if self._root is not None:
            self._root.setParent(None)
            self._root.deleteLater()
            self._root = None

    def show(self):
        return self.Show(
            "Rikugan",
            options=(idaapi.PluginForm.WOPN_TAB | idaapi.PluginForm.WOPN_PERSIST),
        )

    def close(self):
        self.Close(0)

    def shutdown(self) -> None:
        if self._core is not None:
            self._core.shutdown()
            self._core.setParent(None)
            self._core.deleteLater()
            self._core = None

    def prefill_input(self, text: str, auto_submit: bool = False) -> None:
        if self._core is not None:
            self._core.prefill_input(text, auto_submit=auto_submit)

    def on_database_changed(self, new_path: str) -> None:
        if self._core is not None:
            self._core.on_database_changed(new_path)

    def __getattr__(self, name: str):
        # Forward UI action accessors like _input_area / _on_submit.
        core = object.__getattribute__(self, "_core")
        if core is not None and hasattr(core, name):
            return getattr(core, name)
        raise AttributeError(name)
