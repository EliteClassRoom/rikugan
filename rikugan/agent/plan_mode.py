"""Plan mode: generate a plan, get user approval, execute step by step."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    index: int
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: str = ""


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    approved: bool = False
    current_step: int = 0

    @property
    def is_complete(self) -> bool:
        return self.current_step >= len(self.steps)

    def get_current_step(self) -> PlanStep | None:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self) -> None:
        if self.current_step < len(self.steps):
            self.current_step += 1


PLAN_GENERATION_PROMPT = """\
Before executing this task, please create a step-by-step plan.
Format your plan as a numbered list:

1. First step description
2. Second step description
...

After the plan, write "END_PLAN" on its own line.
Do not execute any tools yet — just output the plan.
"""


def parse_plan(text: str) -> list[str]:
    """Parse a numbered plan from LLM output."""
    steps = []
    # Match lines like "1. ...", "2. ...", etc.
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^\d+[\.\)]\s*(.+)$", line)
        if m:
            steps.append(m.group(1).strip())
        if line.upper() == "END_PLAN":
            break
    return steps


def create_plan_from_text(text: str) -> Plan:
    """Parse LLM text into a Plan object."""
    step_texts = parse_plan(text)
    steps = [PlanStep(index=i, description=desc) for i, desc in enumerate(step_texts)]
    return Plan(steps=steps)


def build_step_prompt(plan: Plan) -> str:
    """Build a prompt to execute the current plan step."""
    step = plan.get_current_step()
    if step is None:
        return "The plan is complete."

    context_parts = [f"You are executing step {step.index + 1} of {len(plan.steps)} in your plan."]
    context_parts.append(f"\nCurrent step: {step.description}")

    # Include results of previous steps for context
    prev_results = []
    for s in plan.steps[: step.index]:
        if s.result:
            prev_results.append(f"Step {s.index + 1} ({s.status.value}): {s.result[:200]}")
    if prev_results:
        context_parts.append("\nPrevious step results:")
        context_parts.extend(prev_results)

    context_parts.append(
        "\nExecute this step now using the available tools. Be thorough but focused on this specific step."
    )
    return "\n".join(context_parts)
