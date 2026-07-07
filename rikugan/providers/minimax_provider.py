"""MiniMax provider — Anthropic SDK against MiniMax's compatible API.

MiniMax recommends the Anthropic SDK for integration:
  https://platform.minimax.io/docs/guides/quickstart-sdk

Base URL:  https://api.minimax.io/anthropic
Auth:      plain API key (no OAuth)
"""

from __future__ import annotations

import importlib
from typing import Any, NoReturn

from ..core.errors import (
    AuthenticationError,
    ContextLengthError,
    ProviderError,
    RateLimitError,
)
from ..core.logging import log_debug
from ..core.types import ModelInfo, ProviderCapabilities
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider


class MiniMaxProvider(AnthropicProvider):
    """MiniMax LLM provider using the Anthropic-compatible API at api.minimax.io."""

    DEFAULT_API_BASE = "https://api.minimax.io/anthropic"

    # Model metadata is not exposed by MiniMax's /anthropic/v1/models endpoint,
    # so we maintain it locally and resolve it by model id.  Values follow the
    # MiniMax Anthropic-compatible Messages API documentation.
    _MODEL_LIMITS: dict[str, dict[str, int]] = {
        "MiniMax-M3": {
            "context_window": 1_000_000,
            "max_output_tokens": 524_288,
        },
        "MiniMax-M2.7": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
        "MiniMax-M2.7-highspeed": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
        "MiniMax-M2.5": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
        "MiniMax-M2.5-highspeed": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
        "MiniMax-M2.1": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
        "MiniMax-M2.1-highspeed": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
        "MiniMax-M2": {
            "context_window": 204_800,
            "max_output_tokens": 204_800,
        },
    }

    @classmethod
    def _limits_for_model(cls, model_id: str) -> tuple[int, int]:
        """Return ``(context_window, max_output_tokens)`` for a MiniMax model id.

        MiniMax's /anthropic/v1/models endpoint only returns id/display_name
        metadata — no context or output-token limits — so we resolve them from
        the local ``_MODEL_LIMITS`` table.  Unknown ids fall back to the
        documented M2.x defaults.
        """
        if not model_id:
            limits = cls._MODEL_LIMITS["MiniMax-M2.5"]
        else:
            limits = cls._MODEL_LIMITS.get(model_id) or cls._MODEL_LIMITS["MiniMax-M2.5"]
        return limits["context_window"], limits["max_output_tokens"]

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "MiniMax-M3",
        **kwargs: Any,
    ) -> None:
        # Bypass AnthropicProvider.__init__ — MiniMax uses plain API keys only,
        # no OAuth keychain lookup.
        LLMProvider.__init__(
            self,
            api_key=api_key,
            api_base=api_base or self.DEFAULT_API_BASE,
            model=model,
        )
        self._auth_type = "api_key"

    @property
    def name(self) -> str:
        return "minimax"

    @property
    def capabilities(self) -> ProviderCapabilities:
        # Documented maximum across the MiniMax family — M3 supports a
        # 1M context window and 524288 output tokens.  We expose the
        # largest supported advertised limit so the UI's spin box can be
        # driven by ``ModelInfo.max_output_tokens`` rather than this value.
        return ProviderCapabilities(
            streaming=True,
            tool_use=True,
            vision=False,
            max_context_window=1_000_000,
            max_output_tokens=524_288,
            supports_system_prompt=True,
            supports_cache_control=False,
        )

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                anthropic = importlib.import_module("anthropic")
            except ImportError as exc:
                raise ProviderError(
                    "anthropic package not installed. Run: pip install anthropic",
                    provider="minimax",
                ) from exc
            if not self.api_key:
                raise AuthenticationError(provider="minimax")
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=120.0,  # 2min vs SDK default 10min
            )
        return self._client

    def auth_status(self) -> tuple[str, str]:
        if self.api_key:
            return "API Key", "ok"
        return "", "none"

    @classmethod
    def _builtin_models(cls) -> list[ModelInfo]:
        def _make(model_id: str, display_name: str) -> ModelInfo:
            ctx, max_out = cls._limits_for_model(model_id)
            return ModelInfo(
                id=model_id,
                name=display_name,
                provider="minimax",
                context_window=ctx,
                max_output_tokens=max_out,
                supports_tools=True,
            )

        return [
            _make("MiniMax-M3", "MiniMax M3"),
            _make("MiniMax-M2.7", "MiniMax M2.7"),
            _make("MiniMax-M2.7-highspeed", "MiniMax M2.7 Highspeed"),
            _make("MiniMax-M2.5", "MiniMax M2.5"),
            _make("MiniMax-M2.5-highspeed", "MiniMax M2.5 Highspeed"),
            _make("MiniMax-M2.1", "MiniMax M2.1"),
            _make("MiniMax-M2.1-highspeed", "MiniMax M2.1 Highspeed"),
            _make("MiniMax-M2", "MiniMax M2"),
        ]

    def _fetch_models_live(self) -> list[ModelInfo]:
        try:
            client = self._get_client()
            response = client.models.list(limit=50)
            models: list[ModelInfo] = []
            for m in response.data:
                model_id = m.id
                if not model_id.lower().startswith("minimax"):
                    continue
                ctx, max_out = self._limits_for_model(model_id)
                models.append(
                    ModelInfo(
                        id=model_id,
                        name=getattr(m, "display_name", None) or model_id,
                        provider="minimax",
                        context_window=ctx,
                        max_output_tokens=max_out,
                        supports_tools=True,
                    )
                )
            return models or self._builtin_models()
        except Exception:
            return self._builtin_models()

    def _build_request_kwargs(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
        system: str,
    ) -> dict[str, Any]:
        """Build request kwargs, stripping cache_control (not supported by MiniMax).

        Additionally enables automatic ``thinking`` for ``MiniMax-M3`` (per the
        MiniMax Anthropic-compatible API docs: ``thinking: {"type": "adaptive"}``).
        M2.x models already have thinking permanently enabled and cannot disable
        it, so no explicit ``thinking`` payload is added for them.
        """
        kwargs = super()._build_request_kwargs(messages, tools, temperature, max_tokens, system)

        # System prompt: strip cache_control from blocks
        if isinstance(kwargs.get("system"), list):
            for block in kwargs["system"]:
                block.pop("cache_control", None)
            # If only one plain text block, collapse to a string
            if len(kwargs["system"]) == 1 and kwargs["system"][0].get("type") == "text":
                kwargs["system"] = kwargs["system"][0]["text"]

        # Messages: strip cache_control from content blocks
        for msg in kwargs.get("messages", []):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block.pop("cache_control", None)

        # Tools: strip cache_control
        for tool in kwargs.get("tools", []):
            if isinstance(tool, dict):
                tool.pop("cache_control", None)

        # MiniMax-M3 thinking: enabled automatically.  The MiniMax docs only
        # describe the ``adaptive`` mode for M3 — no manual token budget.
        if (self.model or "").strip().lower() == "minimax-m3":
            kwargs["thinking"] = {"type": "adaptive"}

        return kwargs

    def _handle_api_error(self, e: Exception) -> NoReturn:
        """Translate SDK exceptions to Rikugan errors with MiniMax-aware handling."""
        try:
            anthropic = importlib.import_module("anthropic")
        except ImportError:
            raise ProviderError(str(e), provider="minimax") from e

        # Authentication
        if isinstance(e, anthropic.AuthenticationError):
            raise AuthenticationError(provider="minimax") from e

        # Rate limiting
        if isinstance(e, anthropic.RateLimitError):
            retry_after = 0.0
            resp = getattr(e, "response", None)
            if resp is not None:
                retry_hdr = getattr(resp, "headers", {}).get("retry-after", "")
                try:
                    retry_after = float(retry_hdr)
                except (ValueError, TypeError) as parse_err:
                    log_debug(f"Could not parse retry-after header {retry_hdr!r}: {parse_err}")
            raise RateLimitError(provider="minimax", retry_after=retry_after or 5.0) from e

        # Bad request (context length, etc.) — NOT retryable
        if isinstance(e, anthropic.BadRequestError):
            msg = str(e)
            if "context" in msg.lower() or "token" in msg.lower():
                raise ContextLengthError(str(e), provider="minimax") from e
            raise ProviderError(str(e), provider="minimax") from e

        # Connection errors — RETRYABLE
        if isinstance(e, anthropic.APIConnectionError):
            raise ProviderError(
                f"Connection error: {e}",
                provider="minimax",
                retryable=True,
            ) from e

        # Timeout errors — RETRYABLE
        if isinstance(e, anthropic.APITimeoutError):
            raise ProviderError(
                f"Request timed out: {e}",
                provider="minimax",
                retryable=True,
            ) from e

        # Server errors (500, 502, 503, 504) — RETRYABLE
        if isinstance(e, anthropic.APIStatusError):
            status = getattr(e, "status_code", 0)
            if status >= 500:
                raise ProviderError(
                    f"Server error ({status}): {e}",
                    provider="minimax",
                    status_code=status,
                    retryable=True,
                ) from e
            # Non-retryable status errors
            raise ProviderError(
                f"API error ({status}): {e}",
                provider="minimax",
                status_code=status,
            ) from e

        # Fallback: any other error is NOT retryable
        raise ProviderError(str(e), provider="minimax") from e
