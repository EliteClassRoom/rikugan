"""AOrchestra: agent orchestration with four-tuple φ = ⟨I, C, T, M⟩ specialization."""

from __future__ import annotations

from .context import build_subagent_context, sanitize_context
from .events import (
    OrchestraTurnEvent,
    OrchestraTurnEventType,
    orchestra_approval_request,
    orchestra_cancel,
    orchestra_complete,
    orchestra_delegate,
)
from .main_agent import OrchestraMainAgent
from .orchestra_config import OrchestraConfig, SubAgentSpec
from .subagent_factory import SubAgentFactory

__all__ = [
    "OrchestraConfig",
    "OrchestraMainAgent",
    "OrchestraTurnEvent",
    "OrchestraTurnEventType",
    "SubAgentFactory",
    "SubAgentSpec",
    "build_subagent_context",
    "orchestra_approval_request",
    "orchestra_cancel",
    "orchestra_complete",
    "orchestra_delegate",
    "sanitize_context",
]
