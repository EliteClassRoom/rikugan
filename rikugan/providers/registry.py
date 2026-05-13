"""Provider registry: factory for creating provider instances."""

from __future__ import annotations

import os
from typing import Any

from ..core.errors import ProviderError
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .gemini_provider import GeminiProvider
from .minimax_provider import MiniMaxProvider
from .ollama_provider import DEFAULT_OLLAMA_URL, OllamaProvider
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
        # Keep replaced providers alive for the process lifetime.  In IDA Pro,
        # dropping the last reference to SDK/http clients while Qt/Shiboken is
        # dispatching a signal can run C-level cleanup at an unsafe time.
        self._retired_instances: list[LLMProvider] = []

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
        """Create and cache a new provider instance."""
        instance = self.new_instance(name, api_key=api_key, api_base=api_base, model=model, **kwargs)
        old = self._instances.get(name)
        if old is not None:
            self._retired_instances.append(old)
        self._instances[name] = instance
        return instance

    def new_instance(
        self,
        name: str,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMProvider:
        """Create an uncached provider instance for temporary probes.

        Settings/auth/model-refresh code must use this instead of ``create()``
        so it cannot replace the live chat provider cached in ``_instances``.
        """
        cls = self._providers.get(name)
        if cls is None:
            raise ProviderError(f"Unknown provider: {name}. Available: {self.list_providers()}")

        # Custom OpenAI-compatible providers need their name passed through
        if cls is OpenAICompatProvider and name != "openai_compat":
            kwargs.setdefault("provider_name", name)

        return cls(api_key=api_key, api_base=api_base, model=model, **kwargs)

    def _normalized_api_base(self, name: str, api_base: str) -> str:
        """Return the provider's effective API base for cache comparison."""
        if api_base:
            return api_base
        if name == "minimax":
            return MiniMaxProvider.DEFAULT_API_BASE
        if name == "ollama":
            return os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
        return ""

    def get_or_create(
        self,
        name: str,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMProvider:
        """Get existing instance or create new one.

        Recreates the cached instance only if api_key or api_base changed.
        Model-only switches update the existing provider because SDK clients do
        not bind to a model; the model is included per request.  Replaced
        providers are retained instead of explicitly closed or dropped so SDK
        cleanup cannot run during Qt signal dispatch.
        """
        if name in self._instances:
            inst = self._instances[name]
            key_changed = api_key != inst.api_key
            requested_base = self._normalized_api_base(name, api_base)
            base_changed = requested_base != (inst.api_base or "")
            if key_changed or base_changed:
                return self.create(name, api_key=api_key, api_base=api_base, model=model, **kwargs)
            if model and inst.model != model:
                inst.model = model
            return inst
        return self.create(name, api_key=api_key, api_base=api_base, model=model, **kwargs)

    def get_instance(self, name: str) -> LLMProvider | None:
        return self._instances.get(name)
