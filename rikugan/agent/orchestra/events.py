"""Orchestra-specific turn event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OrchestraTurnEventType(str, Enum):
    DELEGATE = "orchestra_delegate"
    APPROVAL_REQUEST = "orchestra_approval_request"
    DELEGATION_CANCELLED = "orchestra_cancelled"
    COMPLETE = "orchestra_complete"


@dataclass
class OrchestraTurnEvent:
    """Orchestra-specific turn event."""

    type: OrchestraTurnEventType
    agent_id: str = ""
    task_name: str = ""
    instruction: str = ""
    model: str = ""
    tools: list[str] = field(default_factory=list)
    context: str = ""
    result: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def orchestra_delegate(
        agent_id: str,
        task_name: str,
        instruction: str,
        model: str,
        tools: list[str],
        context: str = "",
    ) -> OrchestraTurnEvent:
        return OrchestraTurnEvent(
            type=OrchestraTurnEventType.DELEGATE,
            agent_id=agent_id,
            task_name=task_name,
            instruction=instruction,
            model=model,
            tools=tools,
            context=context,
        )

    @staticmethod
    def orchestra_approval_request(
        agent_id: str,
        task_name: str,
        instruction: str,
        model: str,
        tools: list[str],
        context: str = "",
    ) -> OrchestraTurnEvent:
        return OrchestraTurnEvent(
            type=OrchestraTurnEventType.APPROVAL_REQUEST,
            agent_id=agent_id,
            task_name=task_name,
            instruction=instruction,
            model=model,
            tools=tools,
            context=context,
        )

    @staticmethod
    def orchestra_cancel(agent_id: str, reason: str) -> OrchestraTurnEvent:
        return OrchestraTurnEvent(
            type=OrchestraTurnEventType.DELEGATION_CANCELLED,
            agent_id=agent_id,
            error=reason,
        )

    @staticmethod
    def orchestra_complete(
        agent_id: str,
        task_name: str,
        result: str,
        turn_count: int = 0,
        elapsed: float = 0.0,
    ) -> OrchestraTurnEvent:
        return OrchestraTurnEvent(
            type=OrchestraTurnEventType.COMPLETE,
            agent_id=agent_id,
            task_name=task_name,
            result=result,
            metadata={"turn_count": turn_count, "elapsed": elapsed},
        )


# Backwards compatibility exports
orchestra_delegate = OrchestraTurnEvent.orchestra_delegate
orchestra_approval_request = OrchestraTurnEvent.orchestra_approval_request
orchestra_complete = OrchestraTurnEvent.orchestra_complete
orchestra_cancel = OrchestraTurnEvent.orchestra_cancel
