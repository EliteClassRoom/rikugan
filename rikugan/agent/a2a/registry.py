"""External agent registry — discovers and manages A2A and subprocess agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .client import A2AClient
from .subprocess_bridge import SubprocessBridge
from .types import ExternalAgentConfig

_ORCHESTRA_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "orchestra.toml"


@dataclass
class ExternalAgentRegistry:
    """Registry of external agents (A2A and subprocess-based).

    Auto-discovers CLI agents on PATH and loads user-configured A2A
    agents from the orchestra.toml configuration file.
    """

    agents: list[ExternalAgentConfig] = field(default_factory=list)
    _bridge: SubprocessBridge = field(default_factory=SubprocessBridge, init=False)

    def discover(self) -> list[ExternalAgentConfig]:
        """Discover all available external agents.

        Runs auto-discovery for CLI agents and loads A2A agents from config.
        """
        discovered: list[ExternalAgentConfig] = []

        # Auto-detect CLI agents on PATH
        discovered.extend(self._bridge.discover())

        # Load user-configured A2A agents from orchestra.toml
        discovered.extend(self._load_a2a_agents())

        self.agents = discovered
        return discovered

    def _load_a2a_agents(self) -> list[ExternalAgentConfig]:
        """Load A2A agents from orchestra.toml [[a2a.agents]] sections."""
        import tomllib

        agents: list[ExternalAgentConfig] = []
        if not _ORCHESTRA_CONFIG_PATH.exists():
            return agents

        try:
            with open(_ORCHESTRA_CONFIG_PATH, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return agents

        a2a_config = data.get("a2a", {})
        if not a2a_config:
            return agents

        for agent_spec in a2a_config.get("agents", []):
            if not isinstance(agent_spec, dict):
                continue

            endpoint = agent_spec.get("endpoint", "")
            if not endpoint:
                continue

            # Validate endpoint by trying to discover the agent
            try:
                client = A2AClient(endpoint)
                config = client.discover()
                if config is not None:
                    # Merge with user config (user config takes priority)
                    config.name = agent_spec.get("name", config.name)
                    config.model = agent_spec.get("model", config.model)
                    agents.append(config)
                else:
                    # Agent card not available — trust the config anyway
                    agents.append(
                        ExternalAgentConfig(
                            name=agent_spec.get("name", "unknown"),
                            transport="a2a",
                            endpoint=endpoint,
                            capabilities=agent_spec.get("capabilities", []),
                            model=agent_spec.get("model", ""),
                        )
                    )
            except Exception:
                continue

        return agents

    def list_agents(self) -> list[ExternalAgentConfig]:
        """Return all discovered agents (runs discover if empty)."""
        if not self.agents:
            self.discover()
        return self.agents

    def get_by_name(self, name: str) -> ExternalAgentConfig | None:
        """Find an agent by exact name."""
        for agent in self.list_agents():
            if agent.name == name:
                return agent
        return None

    def get_by_transport(self, transport: Literal["a2a", "subprocess"]) -> list[ExternalAgentConfig]:
        """Return agents filtered by transport type."""
        return [a for a in self.list_agents() if a.transport == transport]
