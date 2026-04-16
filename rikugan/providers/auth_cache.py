"""Cached Anthropic authentication resolution.

Avoids repeated subprocess spawns for OAuth token discovery by caching
the first successful result at module level.  This is the single authority
for auth resolution — both UI and provider construction go through here.
"""

from __future__ import annotations

from .anthropic_provider import resolve_anthropic_auth

_cached_oauth: tuple[str, str] | None = None  # (token, auth_type)
_keychain_consent: bool = False  # set by UI after user accepts OAuth risk


def set_keychain_consent(accepted: bool) -> None:
    """Grant or revoke consent for keychain OAuth autoload."""
    global _keychain_consent
    _keychain_consent = accepted
    if not accepted:
        invalidate_cache()


def resolve_auth_cached(explicit_key: str = "") -> tuple[str, str]:
    """Resolve Anthropic auth, caching the default-key result.

    Only successful resolutions (non-empty token) are cached so that
    transient failures don't stick for the process lifetime.
    """
    global _cached_oauth
    if explicit_key:
        return resolve_anthropic_auth(explicit_key)
    if _cached_oauth is not None:
        return _cached_oauth
    result = resolve_anthropic_auth("", allow_keychain=_keychain_consent)
    # Only cache successful resolutions
    if result[0]:
        _cached_oauth = result
    return result


def has_keychain_token() -> bool:
    """Check if a keychain OAuth token exists (ignoring consent)."""
    token, auth_type = resolve_anthropic_auth("", allow_keychain=True)
    return auth_type == "oauth" and bool(token)


def invalidate_cache() -> None:
    """Clear the cached auth so the next call re-resolves."""
    global _cached_oauth
    _cached_oauth = None
