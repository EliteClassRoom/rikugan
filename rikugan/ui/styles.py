"""Light and Dark theme stylesheets for Rikugan UI.

Light theme based on Monokai Pro Light (Filter Sun) color palette.
Dark theme based on VS Code Dark+.
"""

from __future__ import annotations

_current_theme: str = "light"
# ``_effective_theme`` is the helper palette ('dark' or 'light') that
# inline-styled widgets should look up. For 'ida' the effective theme is
# supplied by the caller (panel core / IDA wrapper) based on the host's
# detected color brightness.
_effective_theme: str = "light"


def set_current_theme(theme: str, effective_theme: str | None = None) -> None:
    """Set the current theme for theme-aware style getters.

    Args:
        theme: The user-configured theme name (``"light"``, ``"dark"``,
            ``"ida"``). ``"ida"`` is treated as "inherit the host".
        effective_theme: Optional helper palette to use when *theme* is
            ``"ida"`` (or any non-``"dark"``/``"light"`` value). Must be
            ``"dark"`` or ``"light"``. When omitted, the previous
            effective theme is preserved (defaulting to ``"light"`` for
            the very first call).
    """
    global _current_theme, _effective_theme
    _current_theme = theme
    if effective_theme in ("dark", "light"):
        _effective_theme = effective_theme
    elif theme in ("dark", "light"):
        _effective_theme = theme
    # If theme is 'ida' and no effective theme was supplied, leave the
    # previous effective theme alone (defaults to "light").


def is_dark_theme() -> bool:
    """Check whether inline-styled widgets should use the dark palette."""
    return _effective_theme == "dark"


def get_current_theme() -> str:
    """Return the user-configured theme name (``"light"``/``"dark"``/``"ida"``).

    ``"ida"`` means "inherit the host's Qt theme".  Use :func:`is_host_theme`
    for a boolean check.
    """
    return _current_theme


def is_host_theme() -> bool:
    """True when the configured theme is ``"ida"`` (inherit the host palette).

    In host-theme mode, Rikugan does not apply its own LIGHT_THEME / DARK_THEME
    global stylesheet.  Inline-styled widgets that have a per-widget
    stylesheet (e.g. the paginated history nav strip) should clear that
    inline stylesheet so the host's Qt stylesheet — or the host-aware
    minimal stylesheet added by the IDA panel wrapper — can take over.

    ``"auto"`` is treated as host-theme for the purposes of the legacy
    helper: the effective palette is decided by the live QApplication,
    and the legacy selectors do not have a separate "auto" branch.
    """
    return _current_theme in ("ida", "auto")


# =============================================================================
# LIGHT THEME - Monokai Pro Light (Filter Sun) inspired
# =============================================================================
LIGHT_THEME = """
QWidget#rikugan_panel {
    background-color: #f8efe7;
    color: #2c232e;
}

QScrollArea#chat_scroll {
    background-color: #f8efe7;
    border: none;
}

QWidget#chat_container {
    background-color: #f8efe7;
}

QFrame#message_user {
    background-color: #f0e8e0;
    border-radius: 8px;
    padding: 8px;
    margin: 4px 8px 4px 8px;
}

QFrame#message_assistant {
    background-color: #f8efe7;
    border-radius: 8px;
    padding: 8px;
    margin: 4px 8px 4px 8px;
}

QFrame#message_tool {
    background-color: #e8e0d8;
    border: 1px solid #d2c9c4;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#message_thinking {
    background-color: #f8efe7;
    border-radius: 6px;
    padding: 4px 8px;
    margin: 2px 8px;
}




QLabel#msg_role_label {
    color: #218871;
    font-weight: bold;
    font-size: inherit;
}

QLabel#tool_header {
    color: #2473b6;
    font-weight: bold;
    font-size: inherit;
}

QLabel#tool_content {
    color: #6851a2;
    font-size: inherit;
}

QLabel#collapse_button {
    border: none;
    color: #92898a;
    font-size: inherit;
}










QLabel#cat_label {
    font-weight: bold;
    font-size: inherit;
}



QLabel#note_title {
    font-weight: bold;
    font-size: inherit;
}

QLabel#note_genre {
    color: #92898a;
    font-size: inherit;
    font-style: italic;
}



QLabel#subagent_icon {
    font-size: inherit;
}

QLabel#subagent_label {
    font-weight: bold;
    font-size: inherit;
}




QLabel#msg_content {
    color: inherit;
}

QLabel#relevance_star {
    color: #d7ba7d;
    font-size: inherit;
}

QFrame#finding_tool {
    border: 1px solid;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#note_tool {
    border: 1px solid;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#subagent_tool {
    border: 1px solid;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#skill_popup {
    background: #f0e8e0;
    border: 1px solid #d2c9c4;
    border-radius: 4px;
    padding: 2px;
}

QFrame#skill_popup QLabel {
    color: #2c232e;
    padding: 3px 8px;
}

QFrame#skill_popup QLabel[selected="true"] {
    background: rgba(177, 104, 3, 0.20);
    border-radius: 3px;
}

QPushButton#option_btn {
    background: #2473b6;
    color: white;
    border: 1px solid #1a5a93;
    border-radius: 4px;
    padding: 4px 14px;
    font-size: inherit;
}

QPushButton#option_btn:hover {
    background: #3d8cd9;
}

QPushButton#option_btn:pressed {
    background: #1a5a93;
}

QPushButton#option_btn:disabled {
    color: #a59c9c;
    background: #e8e0d8;
    border-color: #d2c9c4;
}

QPlainTextEdit#input_area {
    background-color: #f8efe7;
    color: #2c232e;
    border: 1px solid #d2c9c4;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #b16803;
}

QPlainTextEdit#input_area:focus {
    border-color: #2473b6;
}

QPushButton#send_button {
    background-color: #2473b6;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}

QPushButton#send_button:hover {
    background-color: #3d8cd9;
}

QPushButton#send_button:pressed {
    background-color: #1a5a93;
}

QPushButton#send_button:disabled {
    background-color: #e8e0d8;
    color: #92898a;
}

QPushButton#cancel_button {
    background-color: #c0392b;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
}

QFrame#context_bar {
    background-color: #e8e0d8;
    border-top: 1px solid #d2c9c4;
    padding: 4px 8px;
}

QLabel#context_label {
    color: #92898a;
    font-size: inherit;
}

QLabel#context_value {
    color: #2c232e;
    font-size: inherit;
}

QFrame#plan_step {
    background-color: #f0e8e0;
    border: 1px solid #d2c9c4;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}

QFrame#plan_step_active {
    background-color: #f0e8e0;
    border: 1px solid #2473b6;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}

QFrame#plan_step_done {
    background-color: #f0e8e0;
    border: 1px solid #218871;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}

QToolButton#collapse_button {
    border: none;
    color: #92898a;
    font-size: inherit;
}

QToolButton#collapse_button:hover {
    color: #2c232e;
}

QFrame#tools_panel {
    background-color: #f8efe7;
    border-left: 1px solid #d2c9c4;
}

QFrame#tools_panel QTabWidget::pane {
    border: none;
}

QFrame#tools_panel QTabBar {
    background: #f8efe7;
    border: none;
}

QFrame#tools_panel QTabBar::tab {
    background: #f0e8e0;
    color: #72696d;
    padding: 4px 12px;
    border: none;
    border-right: 1px solid #d2c9c4;
    font-size: inherit;
}

QFrame#tools_panel QTabBar::tab:selected {
    background: #f8efe7;
    color: #2c232e;
    border-bottom: 2px solid #218871;
}

QFrame#tools_panel QTabBar::tab:hover {
    background: #e8e0d8;
}

QTreeWidget {
    background-color: #f8efe7;
    color: #2c232e;
    border: none;
    font-size: inherit;
}

QTreeWidget::item {
    padding: 2px 4px;
}

QTreeWidget::item:selected {
    background-color: #d7ba7d;
    color: #2c232e;
}

QTreeWidget::item:hover {
    background-color: #f0e8e0;
}

QHeaderView::section {
    background-color: #e8e0d8;
    color: #2c232e;
    border: none;
    border-right: 1px solid #d2c9c4;
    padding: 3px 6px;
    font-size: inherit;
}

QTableWidget {
    background-color: #f8efe7;
    color: #2c232e;
    border: none;
    gridline-color: #d2c9c4;
    font-size: inherit;
}

QTableWidget::item {
    padding: 2px 4px;
}

QTableWidget::item:selected {
    background-color: #d7ba7d;
    color: #2c232e;
}

QProgressBar {
    background-color: #e8e0d8;
    border: 1px solid #d2c9c4;
    border-radius: 3px;
    text-align: center;
    color: #2c232e;
    font-size: inherit;
    height: 14px;
}

QProgressBar::chunk {
    background-color: #218871;
    border-radius: 2px;
}

QRadioButton {
    color: #2c232e;
    font-size: inherit;
    spacing: 4px;
}

QTextEdit {
    background-color: #f8efe7;
    color: #2c232e;
    border: 1px solid #d2c9c4;
    border-radius: 4px;
    font-size: inherit;
}

QFrame#thinking_block {
    background: #f0e8e0;
    border: 1px solid #d2c9c4;
    border-radius: 6px;
}

QFrame#message_queued {
    border: 1px dashed #2473b6;
    border-radius: 6px;
    background: #f8efe7;
}

QFrame#message_question {
    border: 1px solid #b16803;
    border-radius: 6px;
    background: #f0e8e0;
}

QLabel#error_header {
    color: #ce4770;
    font-weight: bold;
    font-size: inherit;
}

QLabel#error_content {
    color: #2c232e;
    font-size: inherit;
}

QLabel#thinking_header {
    color: #92898a;
    font-size: inherit;
    font-style: italic;
}

QLabel#thinking_content {
    color: #72696d;
    font-size: inherit;
}

QLabel#star_label {
    color: #b16803;
    font-size: inherit;
}

QLabel#phrase_label {
    color: #92898a;
    font-style: italic;
    font-size: inherit;
}

QLabel#queued_badge {
    color: #92898a;
    font-size: inherit;
    font-style: italic;
}

QLabel#question_header {
    color: #b16803;
    font-weight: bold;
    font-size: inherit;
}

QLabel#question_content {
    color: #2c232e;
    font-size: inherit;
}

QLabel#phase_label {
    color: #b16803;
    font-weight: bold;
    font-size: inherit;
}

QLabel#reason_label {
    color: #a59c9c;
    font-size: inherit;
}

QLabel#note_path {
    color: #72696d;
    font-size: inherit;
}

QLabel#note_preview {
    color: #a59c9c;
    font-size: inherit;
}

QLabel#subagent_detail {
    color: #72696d;
    font-size: inherit;
}

QLabel#finding_summary {
    color: #2c232e;
    font-size: inherit;
}

QLabel#addr_label {
    color: #92898a;
    font-size: inherit;
}

QFrame#delegation_approval {
    border: 1px solid #218871;
    border-radius: 6px;
    background: #f0f5f3;
}

QFrame#mutation_entry {
    background: transparent;
}

QLabel#mutation_indicator {
    color: #218871;
    font-size: inherit;
}

QLabel#mutation_desc {
    color: #2c232e;
    font-size: inherit;
}

QLabel#mutation_badge {
    color: #92898a;
    font-size: inherit;
    padding: 1px 4px;
    background: #e8e0d8;
    border-radius: 3px;
}

QPushButton#undo_mutation_btn {
    color: #218871;
    background: #f8efe7;
    border: 1px solid #218871;
    border-radius: 3px;
    padding: 3px 10px;
    font-size: inherit;
}

QPushButton#undo_mutation_btn:hover {
    background: #e8e0d8;
}

QPushButton#undo_mutation_btn:disabled {
    color: #92898a;
    border-color: #92898a;
}

QFrame#bulk_renamer_widget {
    background-color: #f8efe7;
}

QFrame#agent_tree_widget {
    background-color: #f8efe7;
}

QFrame#orchestra_panel {
    background-color: #f8efe7;
}

QLabel#orchestra_header {
    font-size: inherit;
    font-weight: bold;
    color: #218871;
}

QFrame#delegation_dialog {
    background: #1e1e1e;
}

/* History navigation strip (paginated restore) — object-name-scoped
   so generic QPushButton/QLabel styles above do not affect it. */
QFrame#history_nav {
    background: #e8e0d8;
    border: 1px solid #d2c9c4;
    border-radius: 4px;
    padding: 2px 4px;
}

QLabel#history_nav_label {
    color: #72696d;
    font-size: inherit;
    padding: 0 6px;
}

QPushButton#history_nav_btn {
    background: #f0e8e0;
    color: #2c232e;
    border: 1px solid #d2c9c4;
    border-radius: 3px;
    padding: 2px 10px;
    font-size: inherit;
}
QPushButton#history_nav_btn:hover {
    background: #e8e0d8;
}
QPushButton#history_nav_btn:pressed {
    background: #d2c9c4;
}
QPushButton#history_nav_btn:disabled {
    color: #92898a;
    background: #e8e0d8;
    border-color: #d2c9c4;
}
"""

# Dark Theme - VS Code Dark+ inspired
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



QPlainTextEdit#input_area {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    padding: 8px;
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
    font-size: inherit;
}

QLabel#context_value {
    color: #cccccc;
    font-size: inherit;
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
    font-size: inherit;
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
    font-size: inherit;
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
    font-size: inherit;
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
    font-size: inherit;
}

QTableWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    gridline-color: #3c3c3c;
    font-size: inherit;
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
    font-size: inherit;
    height: 14px;
}

QProgressBar::chunk {
    background-color: #4ec9b0;
    border-radius: 2px;
}

QRadioButton {
    color: #d4d4d4;
    font-size: inherit;
    spacing: 4px;
}

QTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    font-size: inherit;
}

QFrame#thinking_block {
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
}

QFrame#message_queued {
    border: 1px dashed #007acc;
    border-radius: 6px;
    background: #1e1e2e;
}

QFrame#message_question {
    border: 1px solid #dcdcaa;
    border-radius: 6px;
    background: #2d2d1e;
}

QLabel#msg_role_label {
    color: #4ec9b0;
    font-weight: bold;
    font-size: inherit;
}

QLabel#tool_header {
    color: #569cd6;
    font-weight: bold;
    font-size: inherit;
}

QLabel#tool_content {
    color: #9cdcfe;
    font-size: inherit;
}

QLabel#collapse_button {
    border: none;
    color: #808080;
    font-size: inherit;
}

QLabel#thinking_header {
    color: #707090;
    font-size: inherit;
    font-style: italic;
}

QLabel#thinking_content {
    color: #606078;
    font-size: inherit;
}

QLabel#star_label {
    color: #dcdcaa;
    font-size: inherit;
}

QLabel#phrase_label {
    color: #808080;
    font-style: italic;
    font-size: inherit;
}

QLabel#queued_badge {
    color: #808080;
    font-size: inherit;
    font-style: italic;
}

QLabel#question_header {
    color: #dcdcaa;
    font-weight: bold;
    font-size: inherit;
}

QLabel#question_content {
    color: #d4d4d4;
    font-size: inherit;
}

QLabel#phase_label {
    color: #d7ba7d;
    font-weight: bold;
    font-size: inherit;
}

QLabel#reason_label {
    color: #b0a070;
    font-size: inherit;
}

QLabel#cat_label {
    font-weight: bold;
    font-size: inherit;
}

QLabel#addr_label {
    color: #808080;
    font-size: inherit;
}

QLabel#finding_summary {
    color: #d4d4d4;
    font-size: inherit;
}

QLabel#note_title {
    font-weight: bold;
    font-size: inherit;
}

QLabel#note_genre {
    color: #808080;
    font-size: inherit;
    font-style: italic;
}

QLabel#note_path {
    color: #606060;
    font-size: inherit;
}

QLabel#note_preview {
    color: #a0a0a0;
    font-size: inherit;
}

QLabel#subagent_icon {
    font-size: inherit;
}

QLabel#subagent_label {
    font-weight: bold;
    font-size: inherit;
}

QLabel#subagent_detail {
    color: #b0b0b0;
    font-size: inherit;
}

QLabel#error_header {
    color: #f44747;
    font-weight: bold;
    font-size: inherit;
}

QLabel#error_content {
    color: #d4d4d4;
    font-size: inherit;
}

QLabel#msg_content {
    color: inherit;
}

QLabel#relevance_star {
    color: #d7ba7d;
    font-size: inherit;
}

QFrame#finding_tool {
    border: 1px solid;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#note_tool {
    border: 1px solid;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#subagent_tool {
    border: 1px solid;
    border-radius: 4px;
    padding: 3px 6px;
    margin: 1px 12px 1px 12px;
}

QFrame#skill_popup {
    border: 1px solid;
    border-radius: 4px;
    padding: 2px;
}

QFrame#skill_popup QLabel {
    padding: 3px 8px;
}

QFrame#skill_popup QLabel[selected="true"] {
    border-radius: 3px;
}

QPushButton#option_btn {
    background: #2d4a6e;
    color: #9cdcfe;
    border: 1px solid #4a7ab5;
    border-radius: 4px;
    padding: 4px 14px;
    font-size: inherit;
}

QPushButton#option_btn:hover {
    background: #3a5a8a;
}

QPushButton#option_btn:pressed {
    background: #1a3a5e;
}

QPushButton#option_btn:disabled {
    color: #808080;
    background: #1e2a3a;
    border-color: #444;
}

QFrame#delegation_approval {
    border: 1px solid #4ec9b0;
    border-radius: 6px;
    background: #1e2e2e;
}

QFrame#mutation_entry {
    background: transparent;
}

QLabel#mutation_indicator {
    color: #4ec9b0;
    font-size: inherit;
}

QLabel#mutation_desc {
    color: #d4d4d4;
    font-size: inherit;
}

QLabel#mutation_badge {
    color: #808080;
    font-size: inherit;
    padding: 1px 4px;
    background: #2d2d2d;
    border-radius: 3px;
}

QPushButton#undo_mutation_btn {
    color: #4ec9b0;
    background: #2d2d2d;
    border: 1px solid #4ec9b0;
    border-radius: 3px;
    padding: 3px 10px;
    font-size: inherit;
}

QPushButton#undo_mutation_btn:hover {
    background: #3d3d3d;
}

QPushButton#undo_mutation_btn:disabled {
    color: #555;
    border-color: #555;
}

QFrame#bulk_renamer_widget {
    background-color: #1e1e1e;
}

QFrame#agent_tree_widget {
    background-color: #1e1e1e;
}

QFrame#orchestra_panel {
    background-color: #1e1e1e;
}

QLabel#orchestra_header {
    font-size: inherit;
    font-weight: bold;
    color: #4ec9b0;
}

QFrame#delegation_dialog {
    background: #1e1e1e;
}

/* History navigation strip (paginated restore) — object-name-scoped
   so generic QPushButton/QLabel styles above do not affect it. */
QFrame#history_nav {
    background: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 2px 4px;
}

QLabel#history_nav_label {
    color: #808080;
    font-size: inherit;
    padding: 0 6px;
}

QPushButton#history_nav_btn {
    background: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 2px 10px;
    font-size: inherit;
}
QPushButton#history_nav_btn:hover {
    background: #3c3c3c;
}
QPushButton#history_nav_btn:pressed {
    background: #1e1e1e;
}
QPushButton#history_nav_btn:disabled {
    color: #555;
    background: #252526;
    border-color: #3c3c3c;
}
"""


# Common UI widget styles moved to ui/theme/widgets_common.py


# Common UI widget style getters moved to ui/theme/widgets_common.py;
# re-exported here so existing 'from .styles import get_*' callers stay unchanged.
# Bulk-renamer style getters moved to ui/theme/widgets_bulk.py;
# re-exported here so existing ``from .styles import get_bulk_*`` callers
# keep working unchanged.
# Agent-tree style getters moved to ui/theme/widgets_agent.py;
# re-exported here so existing 'from .styles import get_agent_*' callers
# keep working unchanged.
from .theme.widgets_agent import (  # noqa: E402,F401 — re-export
    AGENT_BTN_STYLE,
    AGENT_COMBO_STYLE,
    AGENT_PREVIEW_STYLE,
    AGENT_STATUS_COLORS,
    AGENT_STATUS_LABEL_STYLE,
    AGENT_TREE_STYLE,
    get_agent_btn_style,
    get_agent_combo_style,
    get_agent_preview_style,
    get_agent_status_colors,
    get_agent_status_label_style,
    get_agent_tree_style,
)
from .theme.widgets_bulk import (  # noqa: E402,F401 — re-export
    BULK_BTN_STYLE,
    BULK_CHECK_STYLE,
    BULK_COMBO_STYLE,
    BULK_FILTER_STYLE,
    BULK_MODE_LABEL_STYLE,
    BULK_NUM_INPUT_STYLE,
    BULK_PROGRESS_STYLE,
    BULK_RADIO_STYLE,
    BULK_SELECTION_LABEL_STYLE,
    BULK_START_BTN_STYLE,
    BULK_STATUS_COLORS,
    BULK_STOP_BTN_STYLE,
    BULK_TABLE_STYLE,
    get_bulk_btn_style,
    get_bulk_check_style,
    get_bulk_combo_style,
    get_bulk_filter_style,
    get_bulk_mode_label_style,
    get_bulk_num_input_style,
    get_bulk_progress_style,
    get_bulk_radio_style,
    get_bulk_selection_label_style,
    get_bulk_start_btn_style,
    get_bulk_status_colors,
    get_bulk_stop_btn_style,
    get_bulk_table_style,
)
from .theme.widgets_common import (  # noqa: E402,F401 — re-export
    ADD_TAB_BTN_STYLE,
    CANCEL_BTN_STYLE,
    ERR_STATUS_STYLE,
    ERROR_LABEL_STYLE,
    HINT_STATUS_STYLE,
    HISTORY_NAV_BTN_STYLE,
    HISTORY_NAV_FRAME_STYLE,
    HISTORY_NAV_LABEL_STYLE,
    MESSAGE_DIALOG_STYLE,
    MODE_BAR_STYLE,
    OK_STATUS_STYLE,
    PLACEHOLDER_STYLE,
    SETTINGS_BTN_STYLE,
    SMALL_BTN_STYLE,
    SPLITTER_HANDLE_STYLE,
    TAB_WIDGET_STYLE,
    TOOL_COLORS,
    TOOLS_PANEL_BTN_STYLE,
    TOOLS_PANEL_HEADER_STYLE,
    TOOLS_PANEL_STYLE,
    get_add_tab_btn_style,
    get_cancel_btn_style,
    get_err_status_style,
    get_error_label_style,
    get_hint_status_style,
    get_history_nav_button_style,
    get_history_nav_frame_style,
    get_history_nav_label_style,
    get_message_dialog_style,
    get_mode_bar_style,
    get_ok_status_style,
    get_placeholder_style,
    get_settings_btn_style,
    get_small_btn_style,
    get_splitter_handle_style,
    get_tab_widget_style,
    get_tool_colors,
    get_tools_panel_btn_style,
    get_tools_panel_header_style,
    get_tools_panel_style,
)

# Mutation/tool-approval style getters moved to ui/theme/widgets_mutation.py;
# re-exported here so existing 'from .styles import get_mutation*' callers stay unchanged.
from .theme.widgets_mutation import (  # noqa: E402,F401 — re-export
    MUTATION_BADGE_STYLE,
    MUTATION_COUNT_STYLE,
    MUTATION_DESC_STYLE,
    MUTATION_INDICATOR_STYLE,
    MUTATION_TITLE_STYLE,
    MUTATION_UNDO_BTN_STYLE,
    TOOL_APPROVAL_ALLOW_BTN_STYLE,
    TOOL_APPROVAL_ALWAYS_BTN_STYLE,
    TOOL_APPROVAL_CODE_EDITOR_STYLE,
    TOOL_APPROVAL_DENY_BTN_STYLE,
    TOOL_APPROVAL_DISABLED_BTN_STYLE,
    TOOL_APPROVAL_FRAME_STYLE,
    TOOL_APPROVAL_HEADER_STYLE,
    get_mutation_badge_style,
    get_mutation_count_style,
    get_mutation_desc_style,
    get_mutation_indicator_style,
    get_mutation_title_style,
    get_mutation_undo_btn_style,
    get_tool_approval_allow_btn_style,
    get_tool_approval_always_btn_style,
    get_tool_approval_code_editor_style,
    get_tool_approval_deny_btn_style,
    get_tool_approval_disabled_btn_style,
    get_tool_approval_frame_style,
    get_tool_approval_header_style,
)

# Orchestra/delegation/profiles style getters moved to ui/theme/widgets_orchestra.py;
# re-exported here so existing 'from .styles import get_*' callers stay unchanged.
from .theme.widgets_orchestra import (  # noqa: E402,F401 — re-export
    DELEGATION_APPROVAL_WIDGET_STYLE,
    DELEGATION_DIALOG_STYLE,
    DELEGATION_HEADER_STYLE,
    DELEGATION_INFO_STYLE,
    DELEGATION_PREVIEW_STYLE,
    ORCHESTRA_PANEL_STYLE,
    ORCHESTRA_STATS_STYLE,
    PROFILES_BTN_STYLE,
    PROFILES_GROUP_STYLE,
    PROFILES_HEADER_STYLE,
    get_delegation_approval_widget_style,
    get_delegation_dialog_style,
    get_delegation_header_style,
    get_delegation_info_style,
    get_delegation_preview_style,
    get_orchestra_panel_style,
    get_orchestra_stats_style,
    get_profiles_btn_style,
    get_profiles_group_style,
    get_profiles_header_style,
)

# =============================================================================
# Theme-aware style shims (added for theme.manager integration)
# =============================================================================
#
# The production code (panel_core, message_widgets, settings_dialog, etc.)
# imports these helpers from .styles. They previously lived alongside the
# now-removed theme subsystem. The shims below preserve the call sites
# while delegating to either the new ThemeManager or a safe default.
#
# They are deliberately simple — for any visual refinement the manager
# and the styles constants in this module are the source of truth.


def use_native_host_theme() -> bool:
    """Return True when the current theme should inherit the host palette.

    Equivalent to ``is_host_theme()``; provided as a backwards-compatible
    name for callers migrated from the old theme subsystem.
    """
    return is_host_theme()


def host_stylesheet(css: str, fallback: str = "") -> str:
    """Return ``css`` unchanged if the host theme is active, else ``""``.

    When the user selected the "ida" theme we do NOT apply Rikugan's
    inline styles — the host's Qt theme is the source of truth and
    Rikugan's colors would clash with it. For all other themes the
    caller-supplied ``css`` is returned verbatim.

    Callers that want a host-friendly default pass a second argument;
    it is only used in the host-theme branch.
    """
    if is_host_theme():
        return fallback
    return css


def maybe_host_stylesheet(css: str, fallback: str = "") -> str:
    """Alias for :func:`host_stylesheet` (older name)."""
    return host_stylesheet(css, fallback)


def build_theme_stylesheet(widget: object) -> str:
    """Build a minimal theme stylesheet for ``widget``.

    Production path: panel_core already calls individual style getters
    on each child widget. The top-level stylesheet is a no-op here so
    that global QWidget selectors do not bleed into the host (IDA) UI.
    """
    return ""


def build_small_button_stylesheet(widget: object, danger: bool = False) -> str:
    """Build a small-button stylesheet; delegates to the constants above.

    When ``danger=True`` the cancel/remove color palette is used so destructive
    actions (e.g. "Undo All") are visually distinct from regular buttons.
    """
    if danger:
        return CANCEL_BTN_STYLE["dark" if is_dark_theme() else "light"]
    return get_small_btn_style()


# =============================================================================
# Explicit ThemeTokens-based stylesheet builders
# =============================================================================
#
# The functions below build a small QSS string from a ``ThemeTokens``
# instance.  They are used by ``SettingsDialog`` and ``InputArea`` so
# the user-selected Rikugan Light / Dark theme always paints the
# dialog body and the chat input with the chosen palette, even when
# the host's default Qt palette would otherwise leak through as a
# black background in light mode.
#
# The returned QSS uses a ``#rikugan_settings`` / ``#input_area``
# object-name selector so the styles do not bleed into the rest of
# the host application (e.g. IDA's main window).


def build_settings_dialog_stylesheet(tokens: object) -> str:
    """Build a ThemeTokens-driven QSS for ``SettingsDialog``.

    The returned stylesheet targets only widgets under
    ``#rikugan_settings`` (the dialog's object name) and the standard
    editor controls (``QLineEdit``, ``QComboBox``, ``QSpinBox``,
    ``QDoubleSpinBox``, ``QPlainTextEdit``, ``QCheckBox``, ``QLabel``,
    ``QGroupBox``, ``QTabWidget``) so we do not affect any other
    host UI.  In the host/IDA-native mode, returns an empty string
    so the host's palette remains the source of truth.
    """
    if is_host_theme():
        return ""
    base = getattr(tokens, "base", "#ffffff")
    alt_base = getattr(tokens, "alt_base", "#f3f3f3")
    text = getattr(tokens, "text", "#1e1e1e")
    button = getattr(tokens, "button", "#f0f0f0")
    button_text = getattr(tokens, "button_text", "#1e1e1e")
    highlight = getattr(tokens, "highlight", "#0066cc")
    highlight_text = getattr(tokens, "highlight_text", "#ffffff")
    mid = getattr(tokens, "mid", "#cccccc")
    window = getattr(tokens, "window", base)
    return (
        f"#rikugan_settings {{ background-color: {window}; color: {text}; }}"
        f"#rikugan_settings QWidget {{ background-color: {base}; color: {text}; }}"
        f"#rikugan_settings QLabel {{ background: transparent; color: {text}; }}"
        f"#rikugan_settings QGroupBox {{"
        f" background-color: {alt_base}; color: {text};"
        f" border: 1px solid {mid}; border-radius: 4px;"
        f" margin-top: 8px; padding-top: 12px;"
        f"}}"
        f"#rikugan_settings QGroupBox::title {{"
        f" subcontrol-origin: margin; left: 8px; padding: 0 4px;"
        f" color: {text};"
        f"}}"
        f"#rikugan_settings QTabWidget::pane {{"
        f" border: 1px solid {mid}; background: {base};"
        f"}}"
        f"#rikugan_settings QTabBar::tab {{"
        f" background: {alt_base}; color: {text}; padding: 4px 12px;"
        f" border: 1px solid {mid}; border-bottom: none;"
        f" border-top-left-radius: 4px; border-top-right-radius: 4px;"
        f"}}"
        f"#rikugan_settings QTabBar::tab:selected {{"
        f" background: {base}; color: {text};"
        f" border-bottom: 1px solid {base};"
        f"}}"
        f"#rikugan_settings QLineEdit, "
        f"#rikugan_settings QComboBox, "
        f"#rikugan_settings QSpinBox, "
        f"#rikugan_settings QDoubleSpinBox, "
        f"#rikugan_settings QPlainTextEdit {{"
        f" background-color: {base}; color: {text};"
        f" border: 1px solid {mid}; border-radius: 4px;"
        f" padding: 3px 6px; selection-background-color: {highlight};"
        f" selection-color: {highlight_text};"
        f"}}"
        f"#rikugan_settings QLineEdit:focus, "
        f"#rikugan_settings QComboBox:focus, "
        f"#rikugan_settings QSpinBox:focus, "
        f"#rikugan_settings QDoubleSpinBox:focus, "
        f"#rikugan_settings QPlainTextEdit:focus {{"
        f" border-color: {highlight};"
        f"}}"
        f"#rikugan_settings QComboBox QAbstractItemView {{"
        f" background-color: {base}; color: {text};"
        f" border: 1px solid {mid}; selection-background-color: {highlight};"
        f" selection-color: {highlight_text};"
        f"}}"
        f"#rikugan_settings QCheckBox {{ color: {text}; }}"
        f"#rikugan_settings QRadioButton {{ color: {text}; }}"
        f"#rikugan_settings QPushButton {{"
        f" background-color: {button}; color: {button_text};"
        f" border: 1px solid {mid}; border-radius: 4px; padding: 4px 12px;"
        f"}}"
        f"#rikugan_settings QPushButton:hover {{"
        f" background-color: {alt_base};"
        f"}}"
        f"#rikugan_settings QPushButton:pressed {{"
        f" background-color: {mid}; color: {text};"
        f"}}"
        f"#rikugan_settings QDialogButtonBox {{ background: transparent; }}"
    )


def build_input_area_stylesheet(tokens: object) -> str:
    """Build a ThemeTokens-driven QSS for the chat ``InputArea``.

    Targets the ``QPlainTextEdit#input_area`` object name only, so
    the styles do not bleed into other plain text editors in the
    host.  Returns an empty string in host/IDA-native mode.
    """
    if is_host_theme():
        return ""
    base = getattr(tokens, "base", "#ffffff")
    text = getattr(tokens, "text", "#1e1e1e")
    mid = getattr(tokens, "mid", "#cccccc")
    highlight = getattr(tokens, "highlight", "#0066cc")
    highlight_text = getattr(tokens, "highlight_text", "#ffffff")
    return (
        f"QPlainTextEdit#input_area {{"
        f" background-color: {base}; color: {text};"
        f" border: 1px solid {mid}; border-radius: 6px;"
        f" padding: 6px; selection-background-color: {highlight};"
        f" selection-color: {highlight_text};"
        f"}}"
        f"QPlainTextEdit#input_area:focus {{"
        f" border-color: {highlight};"
        f"}}"
    )


def build_skill_popup_stylesheet(tokens: object) -> str:
    """Build a ThemeTokens-driven QSS for the ``_SkillPopup``.

    The popup is a small floating widget, so the QSS targets its
    object name (``#skill_popup``) and child ``QLabel`` children.
    Returns an empty string in host/IDA-native mode.
    """
    if is_host_theme():
        return ""
    alt_base = getattr(tokens, "alt_base", "#f3f3f3")
    text = getattr(tokens, "text", "#1e1e1e")
    mid = getattr(tokens, "mid", "#cccccc")
    highlight = getattr(tokens, "highlight", "#0066cc")
    highlight_text = getattr(tokens, "highlight_text", "#ffffff")
    return (
        f"QFrame#skill_popup {{"
        f" background-color: {alt_base}; color: {text};"
        f" border: 1px solid {mid}; border-radius: 4px; padding: 2px;"
        f"}}"
        f"QFrame#skill_popup QLabel {{"
        f" background: transparent; color: {text}; padding: 3px 8px;"
        f"}}"
        f'QFrame#skill_popup QLabel[selected="true"] {{'
        f" background-color: {highlight}; color: {highlight_text};"
        f" border-radius: 3px;"
        f"}}"
        f'QFrame#skill_popup QLabel[selected="false"] {{'
        f" background-color: {alt_base}; color: {text};"
        f"}}"
    )
