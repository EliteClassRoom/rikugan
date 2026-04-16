"""Light and Dark theme stylesheets for Rikugan UI.

Light theme based on Monokai Pro Light (Filter Sun) color palette.
Dark theme based on VS Code Dark+.
"""

from __future__ import annotations

# Light Theme - Monokai Pro Light (Filter Sun) inspired
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

QLabel#cat_label {
    font-weight: bold;
    font-size: inherit;
}

QLabel#addr_label {
    color: #92898a;
    font-size: inherit;
}

QLabel#finding_summary {
    color: #2c232e;
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

QLabel#note_path {
    color: #72696d;
    font-size: inherit;
}

QLabel#note_preview {
    color: #a59c9c;
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
    color: #72696d;
    font-size: inherit;
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

QLabel#tool_header {
    color: #569cd6;
    font-weight: bold;
    font-size: inherit;
}

QLabel#tool_content {
    color: #9cdcfe;
    font-size: inherit;
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
"""
