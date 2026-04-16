"""Orchestra configuration: SubAgentSpec four-tuple and OrchestraConfig."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ORCHESTRA_CONFIG_DEFAULT = Path(__file__).parent.parent.parent.parent / "orchestra.toml"
SubAgentModel = Literal[
    "claude-sonnet-4-20250514",
    "claude-haiku-4-20250514",
    "gpt-4o-mini",
]


@dataclass
class SubAgentSpec:
    """Four-tuple φ = ⟨I, C, T, M⟩ for sub-agent specialization.

    Attributes:
        instruction: I - Actionable instructions for the sub-agent
        context: C - Curated context from the main agent
        tools: T - Selected tools available to the sub-agent
        model: M - Model to use for the sub-agent
        max_steps: Maximum steps (turns) for the sub-agent
        name: Optional human-readable name for the sub-agent
        mode: Optional mode to run the sub-agent in
            ("exploration" | "explore" | "plan" | "research" | "" for normal)
    """

    instruction: str
    context: str = ""
    tools: list[str] = field(default_factory=list)
    model: str = ""
    max_steps: int = 20
    name: str = ""
    mode: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            first_line = self.instruction.strip().split("\n")[0][:50]
            self.name = first_line or "SubAgent"


@dataclass
class OrchestraConfig:
    """Configuration for the OrchestraMainAgent orchestrator."""

    main_model: str = "claude-sonnet-4-20250514"
    sub_models: list[str] = field(
        default_factory=lambda: [
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250514",
            "gpt-4o-mini",
        ]
    )
    max_delegations: int = 5
    context_window: int = 100
    enable_context_sharing: bool = True
    model_pricing: dict[str, tuple[float, float]] = field(default_factory=dict)
    default_tools: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> OrchestraConfig:
        """Load from TOML file. Returns default config if file missing."""
        import tomllib

        config_path = path or ORCHESTRA_CONFIG_DEFAULT
        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return cls()

        orchestra = data.get("orchestra", {})
        models_pricing = orchestra.get("models", {}).get("pricing", {})
        pricing: dict[str, tuple[float, float]] = {}
        for model_name, price_data in models_pricing.items():
            if isinstance(price_data, dict):
                input_price = price_data.get("input", 0.0)
                output_price = price_data.get("output", 0.0)
                pricing[model_name] = (float(input_price), float(output_price))

        default_tools: dict[str, list[str]] = {}
        for category, tools_list in orchestra.get("default_tools", {}).items():
            if isinstance(tools_list, list):
                default_tools[category] = list(tools_list)

        return cls(
            main_model=orchestra.get("main_model", "claude-sonnet-4-20250514"),
            sub_models=orchestra.get("sub_models", ["claude-sonnet-4-20250514"]),
            max_delegations=orchestra.get("max_delegations", 5),
            context_window=orchestra.get("context_window", 100),
            enable_context_sharing=orchestra.get("enable_context_sharing", True),
            model_pricing=pricing,
            default_tools=default_tools,
        )

    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD for a given token count."""
        pricing = self.model_pricing.get(model)
        if pricing is None:
            return 0.0
        input_cost, output_cost = pricing
        return (prompt_tokens / 1_000_000) * input_cost + (completion_tokens / 1_000_000) * output_cost
