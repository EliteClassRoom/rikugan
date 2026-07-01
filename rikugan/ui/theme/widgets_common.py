"""Common UI widget style builders + getters (token-driven).

Each builder renders a QSS string from the live :class:`ThemeTokens`
resolved via :class:`ThemeManager`, so a theme switch (or the
host-inherited IDA-native palette) flows through to every widget. The
public getter signatures are unchanged from the legacy ``{dark, light}``
dict version so the ~40 call sites in ``panel_core`` / ``message_widgets``
/etc. keep working.

Color-only status dicts (``TOOL_COLORS``) remain branch-keyed dicts:
they return several related colors at once and are consumed as a mapping,
so a builder would add friction without value.
"""

from __future__ import annotations


def _tokens():
    """Return the live ThemeTokens (lazy import to avoid a cycle)."""
    from .manager import ThemeManager

    return ThemeManager.instance().tokens()


def _branch() -> str:
    """Return ``'dark'`` or ``'light'`` for the active effective theme."""
    from ..styles import is_dark_theme  # lazy import to break the cycle

    return "dark" if is_dark_theme() else "light"


# Tool call widget colors — branch-keyed dict (consumed as a mapping).
TOOL_COLORS = {
    "dark": {
        "bullet": "#dcdcaa",
        "status_spinner": "#dcdcaa",
        "status_error": "#f44747",
        "status_success": "#4ec9b0",
        "preview": "#808080",
        "result_header": "#808080",
    },
    "light": {
        "bullet": "#b16803",
        "status_spinner": "#b16803",
        "status_error": "#ce4770",
        "status_success": "#218871",
        "preview": "#92898a",
        "result_header": "#92898a",
    },
}


# === Button builders (all gain :focus + :pressed) ===========================
#
# Every interactive button now carries a visible ``:focus`` ring (border =
# accent token) and a ``:pressed`` tactile feedback, satisfying the
# focus-states + state-clarity rules. The border on hover nudges toward the
# accent so keyboard focus and hover read distinctly.


def _button_qss(t, hover_bg: str, *, object_name: str | None = None) -> str:
    """Shared small-button QSS: button/alt_base/mid/accent tokens.

    ``object_name`` optionally scopes the selectors (e.g. ``#history_nav_btn``)
    so a widget-local stylesheet does not leak to sibling buttons.
    """
    sel = f"QPushButton#{object_name}" if object_name else "QPushButton"
    return (
        f"{sel} {{ background: {t.button}; color: {t.button_text}; "
        f"border: 1px solid {t.mid}; border-radius: 6px; padding: 4px; "
        f"font-size: inherit; }}"
        f"{sel}:hover {{ background: {hover_bg}; border-color: {t.accent}; }}"
        f"{sel}:pressed {{ background: {t.mid}; }}"
        f"{sel}:focus {{ border: 1px solid {t.accent}; }}"
    )


def _small_btn_style() -> str:
    t = _tokens()
    return _button_qss(t, t.alt_base)


def _cancel_btn_style() -> str:
    """Danger variant: error-colored text so destructive actions read."""
    t = _tokens()
    return (
        f"QPushButton {{ background: {t.button}; color: {t.error}; "
        f"border: 1px solid {t.mid}; border-radius: 6px; padding: 4px; "
        f"font-size: inherit; }}"
        f"QPushButton:hover {{ background: {t.alt_base}; border-color: {t.error}; }}"
        f"QPushButton:pressed {{ background: {t.mid}; }}"
        f"QPushButton:focus {{ border: 1px solid {t.accent}; }}"
    )


# Mode bar (Chat | Tools tabs) — accent underline on the active tab
def _mode_bar_style() -> str:
    t = _tokens()
    return (
        f"QTabBar {{ background: {t.button}; border: none; border-bottom: 1px solid {t.mid}; }}"
        f"QTabBar::tab {{ background: {t.button}; color: {t.muted_text}; padding: 4px 16px; "
        f"border: none; border-bottom: 2px solid transparent; font-size: inherit; }}"
        f"QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}"
        f"QTabBar::tab:hover:!selected {{ color: {t.text}; }}"
    )


# Tab widget (chat tabs) — selected tab uses selection token
def _tab_widget_style() -> str:
    t = _tokens()
    return (
        f"QTabWidget::pane {{ border: none; }}"
        f"QTabBar {{ background: {t.window}; border: none; }}"
        f"QTabBar::tab {{ background: {t.alt_base}; color: {t.muted_text}; padding: 2px 8px; "
        f"border: none; border-right: 1px solid {t.mid}; font-size: inherit; max-width: 140px; }}"
        f"QTabBar::tab:selected {{ background: {t.base}; color: {t.highlight_text}; }}"
        f"QTabBar::tab:hover {{ background: {t.button}; }}"
        f"QTabBar::close-button {{ image: none; border: none; padding: 1px; }}"
        f"QTabBar::close-button:hover {{ background: {t.error}; border-radius: 2px; }}"
    )


# Header / placeholder labels (text + muted_text tokens)
def _tools_panel_header_style() -> str:
    t = _tokens()
    return f"color: {t.text}; font-weight: bold; font-size: inherit;"


def _placeholder_style() -> str:
    t = _tokens()
    return f"color: {t.muted_text}; padding: 20px;"


# Tools panel button — radius 4, accent focus
def _tools_panel_btn_style() -> str:
    t = _tokens()
    return (
        f"QPushButton {{ background: {t.button}; color: {t.button_text}; border: 1px solid {t.mid}; "
        f"border-radius: 4px; padding: 2px 8px; font-size: inherit; }}"
        f"QPushButton:hover {{ background: {t.alt_base}; border-color: {t.accent}; }}"
        f"QPushButton:pressed {{ background: {t.mid}; }}"
        f"QPushButton:focus {{ border: 1px solid {t.accent}; }}"
    )


# Tools panel container — accent underline on selected tab
def _tools_panel_style() -> str:
    t = _tokens()
    return f"""
        QWidget#tools_panel {{
            background: {t.window};
        }}
        QTabWidget::pane {{
            border: none;
            background: {t.window};
        }}
        QTabBar::tab {{
            background: {t.button};
            color: {t.muted_text};
            border: 1px solid {t.mid};
            border-bottom: none;
            padding: 5px 14px;
            font-size: inherit;
            min-width: 60px;
        }}
        QTabBar::tab:selected {{
            background: {t.base};
            color: {t.text};
            border-bottom: 2px solid {t.accent};
        }}
        QTabBar::tab:hover:!selected {{
            background: {t.alt_base};
            color: {t.text};
        }}
    """


# Add-tab button (QToolButton) in the chat tab bar
def _add_tab_btn_style() -> str:
    t = _tokens()
    return (
        f"QToolButton {{ color: {t.text}; font-size: inherit; font-weight: bold; "
        f"border: none; background: transparent; }}"
        f"QToolButton:hover {{ background: {t.alt_base}; border-radius: 3px; }}"
        f"QToolButton:focus {{ border: 1px solid {t.accent}; border-radius: 3px; }}"
    )


# Splitter handle
def _splitter_handle_style() -> str:
    t = _tokens()
    return f"QSplitter::handle {{ background: {t.mid}; }}"


# Message dialog (new-chat confirmation) — token-driven, accent focus
def _message_dialog_style() -> str:
    t = _tokens()
    return (
        f"QMessageBox {{ background: {t.window}; color: {t.text}; }}"
        f"QPushButton {{ background: {t.button}; color: {t.button_text}; border: 1px solid {t.mid}; "
        f"border-radius: 4px; padding: 6px 16px; font-size: inherit; min-width: 80px; }}"
        f"QPushButton:hover {{ background: {t.alt_base}; border-color: {t.accent}; }}"
        f"QPushButton:pressed {{ background: {t.mid}; }}"
        f"QPushButton:focus {{ border: 1px solid {t.accent}; }}"
    )


# Error / status labels — semantic tokens
def _error_label_style() -> str:
    t = _tokens()
    return f"color: {t.error};"


def _ok_status_style() -> str:
    t = _tokens()
    return f"color: {t.success}; font-weight: bold;"


def _hint_status_style() -> str:
    t = _tokens()
    return f"color: {t.muted_text};"


def _err_status_style() -> str:
    t = _tokens()
    return f"color: {t.error};"


# History navigation strip (paginated restore)
def _history_nav_frame_style() -> str:
    t = _tokens()
    return (
        f"QFrame#history_nav {{ background: {t.alt_base}; border: 1px solid {t.mid}; "
        f"border-radius: 4px; padding: 2px 4px; }}"
    )


def _history_nav_button_style() -> str:
    t = _tokens()
    return _button_qss(t, t.alt_base, object_name="history_nav_btn") + (
        f"QPushButton#history_nav_btn:disabled {{ color: {t.muted_text}; "
        f"background: {t.alt_base}; border-color: {t.mid}; }}"
    )


def _history_nav_label_style() -> str:
    t = _tokens()
    return f"color: {t.muted_text}; font-size: inherit; padding: 0 6px;"


# Settings button (bold, accent focus)
def _settings_btn_style() -> str:
    t = _tokens()
    return (
        f"QPushButton {{ background: {t.button}; color: {t.button_text}; border: 1px solid {t.mid}; "
        f"border-radius: 4px; font-weight: bold; }}"
        f"QPushButton:hover {{ background: {t.alt_base}; border-color: {t.accent}; }}"
        f"QPushButton:pressed {{ background: {t.mid}; }}"
        f"QPushButton:focus {{ border: 1px solid {t.accent}; }}"
    )


# === Public getters (signatures unchanged from the legacy dict version) =====


def get_small_btn_style() -> str:
    return _small_btn_style()


def get_cancel_btn_style() -> str:
    return _cancel_btn_style()


def get_mode_bar_style() -> str:
    return _mode_bar_style()


def get_tab_widget_style() -> str:
    return _tab_widget_style()


def get_tools_panel_header_style() -> str:
    return _tools_panel_header_style()


def get_placeholder_style() -> str:
    return _placeholder_style()


def get_tools_panel_btn_style() -> str:
    return _tools_panel_btn_style()


def get_tools_panel_style() -> str:
    return _tools_panel_style()


def get_add_tab_btn_style() -> str:
    return _add_tab_btn_style()


def get_splitter_handle_style() -> str:
    return _splitter_handle_style()


def get_message_dialog_style() -> str:
    return _message_dialog_style()


def get_error_label_style() -> str:
    return _error_label_style()


def get_ok_status_style() -> str:
    return _ok_status_style()


def get_hint_status_style() -> str:
    return _hint_status_style()


def get_err_status_style() -> str:
    return _err_status_style()


def get_settings_btn_style() -> str:
    return _settings_btn_style()


def get_history_nav_frame_style() -> str:
    return _history_nav_frame_style()


def get_history_nav_button_style() -> str:
    return _history_nav_button_style()


def get_history_nav_label_style() -> str:
    return _history_nav_label_style()


def get_tool_colors() -> dict[str, str]:
    return TOOL_COLORS[_branch()]
