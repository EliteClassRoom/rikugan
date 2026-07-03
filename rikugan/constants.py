"""Global constants for Rikugan.

This module is data-only — no runtime detection or host probing.
For host capability flags see ``rikugan.core.host``.
"""

from __future__ import annotations

PLUGIN_NAME = "Rikugan"
PLUGIN_VERSION = "1.7.0"
PLUGIN_HOTKEY = "Ctrl+Shift+I"
PLUGIN_COMMENT = "Intelligent Reverse-engineering Integrated System"

# Tool name constants — used wherever the security gate (always-approve
# behavior) and the dispatch tables must agree on the literal string.
# A typo at any of those call sites would silently disable the gate.
EXECUTE_PYTHON_TOOL_NAME = "execute_python"

CONFIG_DIR_NAME = "rikugan"
CONFIG_FILE_NAME = "config.json"
CHECKPOINTS_DIR_NAME = "checkpoints"
CACHE_DIR_NAME = "cache"
STRING_CACHE_SCHEMA_VERSION = 1
STRING_CACHE_BUILD_TIMEOUT = 300.0  # seconds — first-build budget for huge binaries

DEFAULT_MAX_TOKENS = 16384
DEFAULT_TEMPERATURE = 0.2
DEFAULT_CONTEXT_WINDOW = 200000

TOOL_RESULT_TRUNCATE_LEN = 8000

SYSTEM_PROMPT_VERSION = 1
CONFIG_SCHEMA_VERSION = 2
SESSION_SCHEMA_VERSION = 1

SKILLS_DIR_NAME = "skills"
MCP_CONFIG_FILE = "mcp.json"
MCP_TOOL_PREFIX = "mcp_"
MCP_DEFAULT_TIMEOUT = 30.0
