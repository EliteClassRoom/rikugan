"""Common UI widget style dicts + getters.

Extracted verbatim from ``rikugan/ui/styles.py`` to shrink that
mega-module without touching any QSS byte. Each dict carries both its
``dark`` and ``light`` branches; getters select on the live theme flag
read lazily from ``styles`` to avoid an import cycle.
"""

from __future__ import annotations


def _branch() -> str:
    """Return ``'dark'`` or ``'light'`` for the active effective theme."""
    from ..styles import is_dark_theme  # lazy import to break the cycle

    return "dark" if is_dark_theme() else "light"


# Tool call widget colors
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

# Small button style (Send, New, Export, Settings, Tools)
SMALL_BTN_STYLE = {
    "dark": (
        "QPushButton { background: #2d2d2d; color: #d4d4d4; border: 1px solid #3c3c3c; "
        "border-radius: 6px; padding: 4px; font-size: inherit; }"
        "QPushButton:hover { background: #3c3c3c; }"
    ),
    "light": (
        "QPushButton { background: #f0e8e0; color: #2c232e; border: 1px solid #d2c9c4; "
        "border-radius: 6px; padding: 4px; font-size: inherit; }"
        "QPushButton:hover { background: #e8e0d8; }"
    ),
}

# Cancel button style
CANCEL_BTN_STYLE = {
    "dark": (
        "QPushButton { background: #2d2d2d; color: #c42b1c; border: 1px solid #3c3c3c; "
        "border-radius: 6px; padding: 4px; font-size: inherit; }"
        "QPushButton:hover { background: #3c3c3c; }"
    ),
    "light": (
        "QPushButton { background: #f0e8e0; color: #c0392b; border: 1px solid #d2c9c4; "
        "border-radius: 6px; padding: 4px; font-size: inherit; }"
        "QPushButton:hover { background: #e8e0d8; }"
    ),
}

# Mode bar style (Chat | Tools tabs)
MODE_BAR_STYLE = {
    "dark": (
        "QTabBar { background: #2d2d2d; border: none; border-bottom: 1px solid #3c3c3c; }"
        "QTabBar::tab { background: #2d2d2d; color: #808080; padding: 4px 16px; "
        "border: none; border-bottom: 2px solid transparent; font-size: inherit; }"
        "QTabBar::tab:selected { color: #d4d4d4; border-bottom: 2px solid #4ec9b0; }"
        "QTabBar::tab:hover:!selected { color: #d4d4d4; }"
    ),
    "light": (
        "QTabBar { background: #e8e0d8; border: none; border-bottom: 1px solid #d2c9c4; }"
        "QTabBar::tab { background: #e8e0d8; color: #92898a; padding: 4px 16px; "
        "border: none; border-bottom: 2px solid transparent; font-size: inherit; }"
        "QTabBar::tab:selected { color: #2c232e; border-bottom: 2px solid #218871; }"
        "QTabBar::tab:hover:!selected { color: #2c232e; }"
    ),
}

# Tab widget style for chat tabs
TAB_WIDGET_STYLE = {
    "dark": (
        "QTabWidget::pane { border: none; }"
        "QTabBar { background: #1e1e1e; border: none; }"
        "QTabBar::tab { background: #252526; color: #cccccc; padding: 2px 8px; "
        "border: none; border-right: 1px solid #3c3c3c; "
        "font-size: inherit; max-width: 140px; }"
        "QTabBar::tab:selected { background: #1e1e1e; color: #ffffff; }"
        "QTabBar::tab:hover { background: #2d2d2d; }"
        "QTabBar::close-button { image: none; border: none; padding: 1px; }"
        "QTabBar::close-button:hover { background: #c42b1c; border-radius: 2px; }"
    ),
    "light": (
        "QTabWidget::pane { border: none; }"
        "QTabBar { background: #f8efe7; border: none; }"
        "QTabBar::tab { background: #f0e8e0; color: #72696d; padding: 2px 8px; "
        "border: none; border-right: 1px solid #d2c9c4; "
        "font-size: inherit; max-width: 140px; }"
        "QTabBar::tab:selected { background: #f8efe7; color: #2c232e; }"
        "QTabBar::tab:hover { background: #e8e0d8; }"
        "QTabBar::close-button { image: none; border: none; padding: 1px; }"
        "QTabBar::close-button:hover { background: #c0392b; border-radius: 2px; }"
    ),
}

# Tools panel header style
TOOLS_PANEL_HEADER_STYLE = {
    "dark": "color: #d4d4d4; font-weight: bold; font-size: inherit;",
    "light": "color: #2c232e; font-weight: bold; font-size: inherit;",
}

# Placeholder label style (for "Not loaded" labels in tools panel)
PLACEHOLDER_STYLE = {
    "dark": "color: #808080; padding: 20px;",
    "light": "color: #92898a; padding: 20px;",
}

# Tools panel button style
TOOLS_PANEL_BTN_STYLE = {
    "dark": (
        "QPushButton { background: #2d2d2d; color: #d4d4d4; border: 1px solid #3c3c3c; "
        "border-radius: 4px; padding: 2px 8px; font-size: inherit; }"
        "QPushButton:hover { background: #3c3c3c; }"
    ),
    "light": (
        "QPushButton { background: #f0e8e0; color: #2c232e; border: 1px solid #d2c9c4; "
        "border-radius: 4px; padding: 2px 8px; font-size: inherit; }"
        "QPushButton:hover { background: #e8e0d8; }"
    ),
}

# Tools panel stylesheet
TOOLS_PANEL_STYLE = {
    "dark": """
        QWidget#tools_panel {
            background: #1e1e1e;
        }
        QTabWidget::pane {
            border: none;
            background: #1e1e1e;
        }
        QTabBar::tab {
            background: #2d2d2d;
            color: #808080;
            border: 1px solid #3c3c3c;
            border-bottom: none;
            padding: 5px 14px;
            font-size: inherit;
            min-width: 60px;
        }
        QTabBar::tab:selected {
            background: #1e1e1e;
            color: #d4d4d4;
            border-bottom: 2px solid #4ec9b0;
        }
        QTabBar::tab:hover:!selected {
            background: #353535;
            color: #d4d4d4;
        }
    """,
    "light": """
        QWidget#tools_panel {
            background: #f8efe7;
        }
        QTabWidget::pane {
            border: none;
            background: #f8efe7;
        }
        QTabBar::tab {
            background: #f0e8e0;
            color: #72696d;
            border: 1px solid #d2c9c4;
            border-bottom: none;
            padding: 5px 14px;
            font-size: inherit;
            min-width: 60px;
        }
        QTabBar::tab:selected {
            background: #f8efe7;
            color: #2c232e;
            border-bottom: 2px solid #218871;
        }
        QTabBar::tab:hover:!selected {
            background: #e8e0d8;
            color: #2c232e;
        }
    """,
}

# Add button style for tab bar
ADD_TAB_BTN_STYLE = {
    "dark": (
        "QToolButton { color: #d4d4d4; font-size: inherit; font-weight: bold; "
        "border: none; background: transparent; }"
        "QToolButton:hover { background: #3c3c3c; border-radius: 3px; }"
    ),
    "light": (
        "QToolButton { color: #2c232e; font-size: inherit; font-weight: bold; "
        "border: none; background: transparent; }"
        "QToolButton:hover { background: #e8e0d8; border-radius: 3px; }"
    ),
}

# Splitter handle style
SPLITTER_HANDLE_STYLE = {
    "dark": "QSplitter::handle { background: #3c3c3c; }",
    "light": "QSplitter::handle { background: #d2c9c4; }",
}

# Message dialog style for new chat confirmation
MESSAGE_DIALOG_STYLE = {
    "dark": (
        "QMessageBox { background: #1e1e1e; color: #d4d4d4; }"
        "QPushButton { background: #2d2d2d; color: #d4d4d4; border: 1px solid #3c3c3c; "
        "border-radius: 4px; padding: 6px 16px; font-size: inherit; min-width: 80px; }"
        "QPushButton:hover { background: #3c3c3c; }"
    ),
    "light": (
        "QMessageBox { background: #f8efe7; color: #2c232e; }"
        "QPushButton { background: #f0e8e0; color: #2c232e; border: 1px solid #d2c9c4; "
        "border-radius: 4px; padding: 6px 16px; font-size: inherit; min-width: 80px; }"
        "QPushButton:hover { background: #e8e0d8; }"
    ),
}

# Error label style
ERROR_LABEL_STYLE = {
    "dark": "color: #f44747;",
    "light": "color: #ce4770;",
}

# Status label styles
OK_STATUS_STYLE = {
    "dark": "color: #4ec9b0; font-weight: bold;",
    "light": "color: #218871; font-weight: bold;",
}

HINT_STATUS_STYLE = {
    "dark": "color: #808080;",
    "light": "color: #92898a;",
}

ERR_STATUS_STYLE = {
    "dark": "color: #f44747;",
    "light": "color: #ce4770;",
}

# Bulk renamer styles moved to ui/theme/widgets_bulk.py
# Agent-tree styles moved to ui/theme/widgets_agent.py
# Orchestra/delegation/profiles styles moved to ui/theme/widgets_orchestra.py
# Mutation/tool-approval styles moved to ui/theme/widgets_mutation.py
# History navigation strip styles (used by paginated restore in chat_view)
HISTORY_NAV_FRAME_STYLE = {
    "dark": (
        "QFrame#history_nav { background: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 2px 4px; }"
    ),
    "light": (
        "QFrame#history_nav { background: #e8e0d8; border: 1px solid #d2c9c4; border-radius: 4px; padding: 2px 4px; }"
    ),
}

HISTORY_NAV_BTN_STYLE = {
    "dark": (
        "QPushButton#history_nav_btn { background: #2d2d2d; color: #d4d4d4; "
        "border: 1px solid #3c3c3c; border-radius: 3px; padding: 2px 10px; "
        "font-size: inherit; }"
        "QPushButton#history_nav_btn:hover { background: #3c3c3c; }"
        "QPushButton#history_nav_btn:pressed { background: #1e1e1e; }"
        "QPushButton#history_nav_btn:disabled { color: #555; "
        "background: #252526; border-color: #3c3c3c; }"
    ),
    "light": (
        "QPushButton#history_nav_btn { background: #f0e8e0; color: #2c232e; "
        "border: 1px solid #d2c9c4; border-radius: 3px; padding: 2px 10px; "
        "font-size: inherit; }"
        "QPushButton#history_nav_btn:hover { background: #e8e0d8; }"
        "QPushButton#history_nav_btn:pressed { background: #d2c9c4; }"
        "QPushButton#history_nav_btn:disabled { color: #92898a; "
        "background: #e8e0d8; border-color: #d2c9c4; }"
    ),
}

HISTORY_NAV_LABEL_STYLE = {
    "dark": "color: #808080; font-size: inherit; padding: 0 6px;",
    "light": "color: #72696d; font-size: inherit; padding: 0 6px;",
}

# Settings dialog styles
SETTINGS_BTN_STYLE = {
    "dark": (
        "QPushButton { background: #2d2d2d; color: #d4d4d4; border: 1px solid #3c3c3c; "
        "border-radius: 4px; font-weight: bold; }"
        "QPushButton:hover { background: #3c3c3c; }"
    ),
    "light": (
        "QPushButton { background: #f0e8e0; color: #2c232e; border: 1px solid #d2c9c4; "
        "border-radius: 4px; font-weight: bold; }"
        "QPushButton:hover { background: #e8e0d8; }"
    ),
}


def get_small_btn_style() -> str:
    return SMALL_BTN_STYLE[_branch()]


def get_cancel_btn_style() -> str:
    return CANCEL_BTN_STYLE[_branch()]


def get_mode_bar_style() -> str:
    return MODE_BAR_STYLE[_branch()]


def get_tab_widget_style() -> str:
    return TAB_WIDGET_STYLE[_branch()]


def get_tools_panel_header_style() -> str:
    return TOOLS_PANEL_HEADER_STYLE[_branch()]


def get_placeholder_style() -> str:
    return PLACEHOLDER_STYLE[_branch()]


def get_tools_panel_btn_style() -> str:
    return TOOLS_PANEL_BTN_STYLE[_branch()]


def get_tools_panel_style() -> str:
    return TOOLS_PANEL_STYLE[_branch()]


def get_add_tab_btn_style() -> str:
    return ADD_TAB_BTN_STYLE[_branch()]


def get_splitter_handle_style() -> str:
    return SPLITTER_HANDLE_STYLE[_branch()]


def get_message_dialog_style() -> str:
    return MESSAGE_DIALOG_STYLE[_branch()]


def get_error_label_style() -> str:
    return ERROR_LABEL_STYLE[_branch()]


def get_ok_status_style() -> str:
    return OK_STATUS_STYLE[_branch()]


def get_hint_status_style() -> str:
    return HINT_STATUS_STYLE[_branch()]


def get_err_status_style() -> str:
    return ERR_STATUS_STYLE[_branch()]


def get_settings_btn_style() -> str:
    return SETTINGS_BTN_STYLE[_branch()]


def get_history_nav_frame_style() -> str:
    return HISTORY_NAV_FRAME_STYLE[_branch()]


def get_history_nav_button_style() -> str:
    return HISTORY_NAV_BTN_STYLE[_branch()]


def get_history_nav_label_style() -> str:
    return HISTORY_NAV_LABEL_STYLE[_branch()]


def get_tool_colors() -> dict[str, str]:
    return TOOL_COLORS[_branch()]
