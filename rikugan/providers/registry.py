"""Provider registry: factory for creating provider instances.

Provider classes are loaded lazily via import strings — only the actively
requested provider's module is imported on first use, avoiding the cost of
importing all provider SDKs (anthropic, openai, gemini, ollama) at panel boot.

``list_providers()`` does NOT resolve any provider classes — it returns
names from import-spec strings.  ``new_instance()`` resolves exactly the
requested provider class and caches it.
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Union

from ..core.errors import ProviderError
from .base import LLMProvider

# Provider import strings — module_path:ClassName
# Provider SDK modules are only imported when the provider is first requested.
_BUILTIN_PROVIDER_SPECS: dict[str, str] = {
    "anthropic": "rikugan.providers.anthropic_provider:AnthropicProvider",
    "openai": "rikugan.providers.openai_provider:OpenAIProvider",
    "openai_compat": "rikugan.providers.openai_compat:OpenAICompatProvider",
    "gemini": "rikugan.providers.gemini_provider:GeminiProvider",
    "ollama": "rikugan.providers.ollama_provider:OllamaProvider",
    "minimax": "rikugan.providers.minimax_provider:MiniMaxProvider",
}

# A provider entry is either an import spec string ("module:ClassName")
# or an already-resolved class instance (for in-process register()).
ProviderEntry = Union[str, type[LLMProvider]]


class ProviderRegistry:
    """Factory for creating and managing LLM providers.

    Provider entries are stored as import-spec strings until a specific
    provider is requested.  This avoids importing every provider SDK module
    at startup — only the actively used provider's adapter module is imported.

    Custom OpenAI-compatible provider names are tracked per-instance (not
    at module level) so that multiple registries coexist without polluting
    each other.  Names registered via ``register()`` (in-process classes)
    are distinguished from config-based custom providers and are preserved
    across ``register_custom_providers()`` calls.
    """

    def __init__(self) -> None:
        # Map provider name → import spec string or resolved class.
        # Initialized from built-in spec strings without resolving any classes.
        self._providers: dict[str, ProviderEntry] = dict(_BUILTIN_PROVIDER_SPECS)
        self._instances: dict[str, LLMProvider] = {}
        # Keep replaced providers alive for the process lifetime.  In IDA Pro,
        # dropping the last reference to SDK/http clients while Qt/Shiboken is
        # dispatching a signal can run C-level cleanup at an unsafe time.
        self._retired_instances: list[LLMProvider] = []

        # Instance-local tracking.
        # _openai_compat_names: custom provider names that resolve to the
        #   openai_compat adapter (registered via register_custom_providers).
        # _registered_names: names registered via register() (in-process class)
        #   — these are NOT removed by register_custom_providers() cleanup.
        self._openai_compat_names: set[str] = set()
        self._registered_names: set[str] = set()

    def _resolve_entry(self, name: str) -> type[LLMProvider]:
        """Resolve a named entry to its provider class.

        If the entry is still an import spec string, the module is imported
        now and the resolved class is cached in place.  If the entry is
        already a resolved class (from ``register()``), it is returned directly.
        """
        entry = self._providers.get(name)
        if entry is None:
            raise ProviderError(
                f"Unknown provider: {name}. Available: {self.list_providers()}"
            )
        if isinstance(entry, str):
            mod_path, cls_name = entry.rsplit(":", 1)
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            self._providers[name] = cls
            return cls
        return entry

    def _is_compat_name(self, name: str) -> bool:
        """Return True if *name* is a custom OpenAI-compatible provider.

        Uses the instance-local set — does NOT import or resolve any
        provider classes.
        """
        if name == "openai_compat":
            return True
        return name in self._openai_compat_names

    def register(self, name: str, provider_cls: type[LLMProvider]) -> None:
        """Register an in-process provider class (bypasses import strings)."""
        self._providers[name] = provider_cls
        self._registered_names.add(name)
        self._openai_compat_names.discard(name)

    def unregister(self, name: str) -> None:
        """Remove a provider entry by name.

        Only removes entries that are not built-in.  Built-in providers
        and the active cached instance are not affected.
        """
        if name in _BUILTIN_PROVIDER_SPECS:
            return
        self._providers.pop(name, None)
        self._openai_compat_names.discard(name)
        self._registered_names.discard(name)

    def register_custom_providers(self, names: list[str]) -> None:
        """Register custom provider names as OpenAI-compatible endpoints.

        Does NOT import the OpenAI-compatible adapter module — the entry
        is stored as the same import spec string used for "openai_compat"
        and will be resolved on first use.

        Names that were previously registered via config but are absent
        from *names* are removed.  Providers registered via ``register()``
        (in-process classes) and built-in entries are never removed.
        """
        compat_spec = _BUILTIN_PROVIDER_SPECS["openai_compat"]
        new_set = set(names)

        # Remove custom providers no longer in the latest config.
        # Skip built-in entries and entries registered via register()
        # (in-process classes) — they are not config-managed.
        for existing_name in list(self._providers.keys()):
            if existing_name in _BUILTIN_PROVIDER_SPECS:
                continue
            if existing_name in self._registered_names:
                continue
            if existing_name not in new_set:
                self._providers.pop(existing_name, None)
                self._openai_compat_names.discard(existing_name)
                # Also retire any live instance so it doesn't hang around
                retired = self._instances.pop(existing_name, None)
                if retired is not None:
                    self._retired_instances.append(retired)

        # Add or re-add current config entries.
        for name in names:
            if name in _BUILTIN_PROVIDER_SPECS:
                continue
            if name in self._registered_names:
                continue
            if name not in self._providers:
                self._providers[name] = compat_spec
            self._openai_compat_names.add(name)

    def list_providers(self) -> list[str]:
        """Return all known provider names without importing any adapter modules."""
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

        Only the requested provider's adapter module is imported.  For custom
        OpenAI-compatible names, the ``openai_compat`` adapter is resolved
        on-demand (not eagerly).
        """
        cls = self._resolve_entry(name)

        if self._is_compat_name(name) and name != "openai_compat":
            kwargs.setdefault("provider_name", name)

        return cls(api_key=api_key, api_base=api_base, model=model, **kwargs)

    def _normalized_api_base(self, name: str, api_base: str) -> str:
        """Return the provider's effective API base for cache comparison."""
        if api_base:
            return api_base
        if name == "minimax":
            cls = self._resolve_entry("minimax")
            return getattr(cls, "DEFAULT_API_BASE", "")
        if name == "ollama":
            from .ollama_provider import DEFAULT_OLLAMA_URL

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
        cached = self._instances.get(name)
        if cached is not None:
            normalized_new = self._normalized_api_base(name, api_base)
            normalized_old = self._normalized_api_base(name, cached.api_base)
            if normalized_new == normalized_old and api_key == cached.api_key:
                if model and cached.model != model:
                    cached.model = model
                return cached
            # Key or base changed — replace
            self._retired_instances.append(cached)

        instance = self.new_instance(name, api_key=api_key, api_base=api_base, model=model, **kwargs)
        self._instances[name] = instance
        return instance

    def get_instance(self, name: str) -> LLMProvider | None:
        """Return a cached provider instance by name, or None.

        Does NOT create a new instance and does NOT import provider
        modules.  External integrations and tests use this to access
        pre-existing instances without side effects.
        """
        return self._instances.get(name)

    def reset(self) -> None:
        """Remove all non-built-in providers and cached instances.

        Useful after a full config reload to clear stale entries while
        keeping built-in specs.
        """
        self._providers = dict(_BUILTIN_PROVIDER_SPECS)
        self._openai_compat_names.clear()
        self._registered_names.clear()
        # Retire all instances to avoid unsafe cleanup
        self._retired_instances.extend(self._instances.values())
        self._instances.clear()
