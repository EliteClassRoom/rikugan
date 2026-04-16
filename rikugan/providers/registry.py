"""Provider registry: factory for creating provider instances."""

from __future__ import annotations

from typing import Any

from ..core.errors import ProviderError
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .gemini_provider import GeminiProvider
from .minimax_provider import MiniMaxProvider
from .ollama_provider import OllamaProvider
from .openai_compat import OpenAICompatProvider
from .openai_provider import OpenAIProvider

_BUILTIN_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "openai_compat": OpenAICompatProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "minimax": MiniMaxProvider,
}


class ProviderRegistry:
    """Factory for creating and managing LLM providers."""

    def __init__(self) -> None:
        self._providers: dict[str, type[LLMProvider]] = dict(_BUILTIN_PROVIDERS)
        self._instances: dict[str, LLMProvider] = {}

    def register(self, name: str, provider_cls: type[LLMProvider]) -> None:
        self._providers[name] = provider_cls

    def register_custom_providers(self, names: list[str]) -> None:
        """Register custom provider names as OpenAI-compatible endpoints."""
        for name in names:
            if name not in _BUILTIN_PROVIDERS:
                self._providers[name] = OpenAICompatProvider

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    def create(
        self,
        name: str,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMProvider:
        """Create a new provider instance."""
        cls = self._providers.get(name)
        if cls is None:
            raise ProviderError(f"Unknown provider: {name}. Available: {self.list_providers()}")

        # Custom OpenAI-compatible providers need their name passed through
        if cls is OpenAICompatProvider and name != "openai_compat":
            kwargs.setdefault("provider_name", name)

        instance = cls(api_key=api_key, api_base=api_base, model=model, **kwargs)
        self._instances[name] = instance
        return instance

    def get_or_create(
        self,
        name: str,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMProvider:
        """Get existing instance or create new one.

        Recreates the instance if api_key or api_base changed.
        """
        if name in self._instances:
            inst = self._instances[name]
            key_changed = api_key != inst.api_key
            base_changed = api_base != (inst.api_base or "")
            if key_changed or base_changed:
                return self.create(name, api_key=api_key, api_base=api_base, model=model, **kwargs)
            if model and inst.model != model:
                inst.model = model
            return inst
        return self.create(name, api_key=api_key, api_base=api_base, model=model, **kwargs)

    def get_instance(self, name: str) -> LLMProvider | None:
        return self._instances.get(name)
