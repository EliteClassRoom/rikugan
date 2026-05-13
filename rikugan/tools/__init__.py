"""Shared tool framework: @tool decorator, ToolRegistry, and security helpers.

Host-specific tool implementations live in their respective packages:
  - rikugan.ida.tools   (IDA Pro)
  - rikugan.binja.tools (Binary Ninja)
"""

from . import base, functions, web, web_fetch

__all__ = ["base", "functions", "web", "web_fetch"]
