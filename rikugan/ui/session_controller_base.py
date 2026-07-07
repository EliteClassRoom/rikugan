"""Host-agnostic session controller orchestration.

Performance note
----------------
The agent runtime (``AgentLoop``, ``BackgroundAgentRunner``, ``MCPManager``,
``ProviderRegistry``, ``SkillRegistry``, ``SessionState``, ``SessionHistory``)
is a heavy import chain (~25ms cold). It is needed to actually drive a
chat session, but the panel is created long before the user sends a
first message. We defer the imports into the methods that need them so
the panel-construction path stays light.
"""

from __future__ import annotations

import copy
import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..core.config import RikuganConfig
from ..core.host import get_database_instance_id, set_database_instance_id
from ..core.logging import log_debug, log_error, log_info, log_warning

if TYPE_CHECKING:
    from ..agent.loop import AgentLoop, BackgroundAgentRunner
    from ..agent.turn import TurnEvent
    from ..mcp.manager import MCPManager
    from ..providers.base import LLMProvider
    from ..providers.registry import ProviderRegistry
    from ..skills.registry import SkillRegistry
    from ..state.history import SessionHistory
    from ..state.session import SessionState
    from ..tools.registry import ToolRegistry
else:
    AgentLoop = BackgroundAgentRunner = TurnEvent = None  # type: ignore[assignment]
    MCPManager = ProviderRegistry = SkillRegistry = None  # type: ignore[assignment]
    SessionHistory = SessionState = None  # type: ignore[assignment]
    ToolRegistry = Any


def _normalize_db_path(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))
    except OSError:
        return path


class SessionControllerBase:
    """Non-Qt orchestrator for Rikugan sessions."""

    def __init__(
        self,
        config: RikuganConfig,
        tool_registry_factory: Callable[[], ToolRegistry],
        database_path_getter: Callable[[], str],
        host_name: str,
        ensure_tools_ready: Callable[[Any], Any] | None = None,
        reset_deferred_tools: Callable[[], None] | None = None,
    ):
        # Lazy imports — keep heavy agent runtime off the panel-import
        # path. Each import is performed at most once per process; we
        # cache the imported symbols back into the module globals so
        # subsequent calls (and any sibling code) see them immediately.
        global AgentLoop, BackgroundAgentRunner, TurnEvent
        global MCPManager, ProviderRegistry, SkillRegistry
        global SessionHistory, SessionState
        if AgentLoop is None:
            from ..agent.loop import AgentLoop as _AgentLoop
            from ..agent.loop import BackgroundAgentRunner as _BackgroundAgentRunner
            from ..agent.turn import TurnEvent as _TurnEvent
            from ..mcp.manager import MCPManager as _MCPManager
            from ..providers.registry import ProviderRegistry as _ProviderRegistry
            from ..skills.registry import SkillRegistry as _SkillRegistry
            from ..state.history import SessionHistory as _SessionHistory
            from ..state.session import SessionState as _SessionState

            AgentLoop = _AgentLoop
            BackgroundAgentRunner = _BackgroundAgentRunner
            TurnEvent = _TurnEvent
            MCPManager = _MCPManager
            ProviderRegistry = _ProviderRegistry
            SkillRegistry = _SkillRegistry
            SessionHistory = _SessionHistory
            SessionState = _SessionState

        self.config = config
        self.host_name = host_name
        self._provider_registry = ProviderRegistry()
        self._provider_registry.register_custom_providers(list(config.custom_providers.keys()))
        # Build the tool registry eagerly on the IDA/main thread.
        #
        # The factory typically imports the host's tool module tree
        # (``ida_funcs`` etc.), which AGENTS.md flags as a Shiboken
        # UAF risk on non-main threads (Python > 3.10). Calling it
        # here — in __init__, which the host invokes synchronously
        # from the plugin entry point — keeps every import on the
        # main thread and prevents the background ``_initialize_runtime``
        # from racing with ``start_agent`` over the same factory.
        self._tool_registry_factory = tool_registry_factory
        self._tool_registry: ToolRegistry = tool_registry_factory()
        self._skill_registry = SkillRegistry()
        self._mcp_manager = MCPManager()
        self._idb_path = _normalize_db_path(database_path_getter())
        self._db_instance_id = self._ensure_db_instance_id()
        self._runtime_init_done = threading.Event()
        self._runtime_shutdown = threading.Event()
        # Host-provided callbacks for advanced/deferred tool registration.
        # The base class does not import IDA modules — host subclasses
        # wire the actual registration function in (e.g. IDA Pro passes
        # ``register_advanced_tools`` from ``rikugan.ida.tools.registry``).
        self._advanced_tools_registered = False
        self._ensure_tools_ready = ensure_tools_ready
        self._reset_deferred_tools = reset_deferred_tools
        self._runtime_init_thread = threading.Thread(
            target=self._initialize_runtime,
            daemon=True,
            name="rikugan-runtime-init",
        )
        self._runtime_init_thread.start()

        # Multi-tab session management
        self._sessions: dict[str, SessionState] = {}
        self._active_tab_id: str = ""
        tab_id = self._create_session()
        self._active_tab_id = tab_id

        self._runner: BackgroundAgentRunner | None = None
        self._pending_messages: list[str] = []
        # Snapshot of the skill-relevant config fields so ``update_settings``
        # can skip the expensive ``_reload_skills`` filesystem rescan when
        # only non-skill config (provider/model/theme) changed. Theme-only
        # and provider-only edits used to pay the full discovery cost.
        self._skill_config_signature = self._compute_skill_config_signature()

    def _compute_skill_config_signature(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return an order-insensitive snapshot of the skill-relevant config.

        These two fields are what :meth:`_reload_skills` feeds into
        :meth:`SkillRegistry.load_external_skills`, so they are the only
        fields whose change requires a reload. Comparing the signature
        before/after a Settings round-trip lets us skip the filesystem
        scan when the user only flipped the theme or the model.
        """
        return (
            tuple(sorted(self.config.enabled_external_skills)),
            tuple(sorted(self.config.disabled_skills)),
        )

    def _initialize_runtime(self) -> None:
        """Load heavy runtime components off the UI path."""
        started = time.perf_counter()
        try:
            if self._runtime_shutdown.is_set():
                return
            self._skill_registry.discover()

            # Apply disabled skills + load enabled external skills
            self._skill_registry.load_external_skills(
                self.config.enabled_external_skills,
                self.config.disabled_skills,
            )

            if self._runtime_shutdown.is_set():
                return
            self._mcp_manager.load_config()

            enabled_set = set(self.config.enabled_external_mcp)
            if enabled_set:
                # Load enabled external MCP servers only when explicitly configured.
                from ..core.external_sources import discover_all_external_mcp

                external_mcp = discover_all_external_mcp()
                for source_key, servers in external_mcp.items():
                    enabled = [s for s in servers if f"{source_key}:{s.name}" in enabled_set]
                    if enabled:
                        self._mcp_manager.add_external_configs(enabled)

            if self._runtime_shutdown.is_set():
                return
            self._mcp_manager.start_servers(self.tool_registry)
        except Exception as e:
            log_error(f"Background runtime initialization failed: {e}")
        finally:
            self._runtime_init_done.set()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            log_debug(f"Runtime initialization completed in {elapsed_ms} ms")

    # --- Instance ID ---

    @staticmethod
    def _ensure_db_instance_id() -> str:
        """Read or generate a database-instance UUID for the current IDB."""
        existing = get_database_instance_id()
        if existing:
            log_debug(f"Database instance ID: {existing}")
            return existing
        new_id = uuid.uuid4().hex
        if set_database_instance_id(new_id):
            log_info(f"Generated new database instance ID: {new_id}")
            return new_id
        # Standalone or write failure — use an ephemeral ID (won't persist)
        log_debug("Could not persist database instance ID, using ephemeral")
        return new_id

    # --- Tab / multi-session management ---

    def _create_session(self) -> str:
        """Create a new SessionState and return its tab_id."""
        tab_id = uuid.uuid4().hex[:8]
        session = SessionState(
            provider_name=self.config.provider.name,
            model_name=self.config.provider.model,
            idb_path=self._idb_path,
            db_instance_id=self._db_instance_id,
        )
        self._sessions[tab_id] = session
        return tab_id

    def create_tab(self) -> str:
        """Create a new tab with a fresh session. Returns tab_id."""
        tab_id = self._create_session()
        log_info(f"Created new tab {tab_id}")
        return tab_id

    def fork_session(self, source_tab_id: str) -> str | None:
        """Duplicate a session into a new tab. Returns new tab_id or None."""
        source = self._sessions.get(source_tab_id)
        if source is None:
            return None
        new_tab_id = uuid.uuid4().hex[:8]
        forked = SessionState(
            provider_name=source.provider_name,
            model_name=source.model_name,
            idb_path=source.idb_path,
            db_instance_id=source.db_instance_id,
        )
        forked.messages = copy.deepcopy(source.messages)
        forked.total_usage = copy.copy(source.total_usage)
        forked.last_prompt_tokens = source.last_prompt_tokens
        forked.current_turn = source.current_turn
        forked.metadata = dict(source.metadata)
        forked.metadata["forked_from"] = source.id
        self._sessions[new_tab_id] = forked
        log_info(f"Forked session {source.id} → new tab {new_tab_id}")
        return new_tab_id

    def close_tab(self, tab_id: str) -> None:
        """Save and remove a tab's session."""
        session = self._sessions.get(tab_id)
        if session is None:
            return
        if self.config.checkpoint_auto_save and session.messages:
            try:
                history = SessionHistory(self.config)
                history.save_session(session)
            except (OSError, ValueError) as e:
                log_error(f"Failed to save session on tab close: {e}")
        del self._sessions[tab_id]
        log_debug(f"Closed tab {tab_id}")

    def switch_tab(self, tab_id: str) -> None:
        """Switch active tab. Cancels running agent if switching away."""
        if tab_id == self._active_tab_id:
            return
        if tab_id not in self._sessions:
            return
        if self.is_agent_running:
            self.cancel()
        self._active_tab_id = tab_id
        log_debug(f"Switched to tab {tab_id}")

    def tab_label(self, tab_id: str) -> str:
        """Return a display label for a tab."""
        session = self._sessions.get(tab_id)
        if session is None:
            return "New Chat"
        for msg in session.messages:
            if msg.role.value == "user" and msg.content:
                text = msg.content.strip()
                return text[:20] + ("..." if len(text) > 20 else "")
        return "New Chat"

    @property
    def active_tab_id(self) -> str:
        return self._active_tab_id

    @property
    def tab_ids(self) -> list[str]:
        return list(self._sessions.keys())

    @property
    def session(self) -> SessionState:
        return self._sessions[self._active_tab_id]

    def get_session(self, tab_id: str) -> SessionState | None:
        return self._sessions.get(tab_id)

    @property
    def provider_registry(self) -> ProviderRegistry:
        return self._provider_registry

    @property
    def tool_registry(self) -> ToolRegistry:
        # The registry is built eagerly in ``__init__`` so the IDA
        # module imports land on the main thread. This is a plain
        # getter; do NOT make it lazy — the original lazy form
        # triggered a Shiboken UAF on Python > 3.10 when the property
        # was first accessed from the ``_initialize_runtime`` background
        # thread.
        return self._tool_registry

    @property
    def skill_slugs(self) -> list[str]:
        if not self._runtime_init_done.is_set():
            return []
        return self._skill_registry.list_slugs()

    @property
    def runtime_ready(self) -> bool:
        return self._runtime_init_done.is_set()

    @property
    def is_agent_running(self) -> bool:
        return self._runner is not None and self._runner.agent_loop.is_running

    def get_runner(self) -> BackgroundAgentRunner | None:
        return self._runner

    def get_provider(self) -> LLMProvider | None:
        """Create and return an LLMProvider instance for the current config.

        Returns None when provider construction or ensure_ready fails (failure
        is logged via ``log_error``); callers must defensively handle this.
        """
        try:
            return self._create_provider()
        except Exception as e:
            log_error(f"Provider creation failed: {e}")
            return None

    def get_tool_registry(self) -> ToolRegistry:
        """Return the lazily-created tool registry."""
        return self.tool_registry

    # --- Advanced / deferred tool registration (host-provided) ---

    def ensure_advanced_tools_ready(self) -> bool:
        """Register host-specific advanced tool modules, if a callback was provided.

        The base class does not know about IDA/Binja/Hex-Rays — host
        subclasses pass a callable in ``__init__`` (e.g.
        ``register_advanced_tools`` from ``rikugan.ida.tools.registry``).
        The call is idempotent and never raises: failures are logged
        and a retry is attempted on the next prompt or settings reload.

        Returns True when all modules registered (or the host does not
        provide advanced registration), False when at least one module
        failed and may be retried later.
        """
        if self._advanced_tools_registered:
            return True
        if self._ensure_tools_ready is None:
            self._advanced_tools_registered = True
            return True
        try:
            result = self._ensure_tools_ready(self.tool_registry)
        except Exception as e:
            log_warning(f"Advanced tool registration failed: {e}")
            return False
        ok = bool(getattr(result, "ok", True))
        if not ok:
            failed = getattr(result, "failed_modules", []) or []
            log_warning(
                "Advanced tool registration partially failed: "
                f"{len(failed)} modules ({', '.join(failed)}). "
                "Will retry on next prompt or settings reload."
            )
            return False
        registered = int(getattr(result, "registered", 0) or 0)
        self._advanced_tools_registered = True
        log_info(f"Advanced tool registration complete ({registered} tools)")
        return True

    def reset_deferred_tools(self) -> None:
        """Reset the deferred-registration retry state.

        The host may need to retry every module (not just the
        previously-failed ones) after the operator changes environment
        state (e.g. installs Hex-Rays).  The optional
        ``reset_deferred_tools`` callback is invoked first so the host
        can clear its own bookkeeping; we then clear the cached
        "already-registered" flag so the next call to
        :func:`ensure_advanced_tools_ready` re-imports everything.
        """
        if self._reset_deferred_tools is not None:
            try:
                self._reset_deferred_tools()
            except Exception as e:
                log_warning(f"Failed to reset deferred tool state: {e}")
        self._advanced_tools_registered = False

    def _create_provider(self) -> Any:
        """Create (or fetch) an LLMProvider instance for the current config.

        Centralised so OAuth/keychain consent prompts and MiniMax web
        config sync run exactly once per provider creation. Host
        subclasses may override to add custom side effects.
        """
        if not self._runtime_init_done.is_set():
            self._runtime_init_done.wait(timeout=10.0)
        # Apply OAuth keychain consent for Anthropic before creating the
        # provider so the provider does not see a "missing" key on the
        # first run.
        try:
            from ..providers.auth_cache import resolve_auth_cached

            resolve_auth_cached(self.config.provider.api_key or "")
        except Exception as exc:
            log_debug(f"Session auth cache warm-up failed: {exc}")
        provider = self._provider_registry.get_or_create(
            self.config.provider.name,
            api_key=self.config.provider.api_key,
            api_base=self.config.provider.api_base,
            model=self.config.provider.model,
        )
        # Let ``ensure_ready`` raise: ``start_agent`` and ``get_provider``
        # both wrap this call in a try/except and surface the failure as
        # a user-facing "Provider error" string. Silently swallowing a
        # broken-provider here would feed a half-initialised provider to
        # ``AgentLoop`` and crash the loop with an opaque traceback.
        provider.ensure_ready()
        return provider

    def _sync_web_tool_config(self) -> None:
        """Sync MiniMax web tool runtime config + capabilities onto the registry.

        Mirrors ``start_agent``'s pre-loop side effect: web tools need
        the active config baked in before the LLM sees the tool schema,
        and the registry's capability flags must reflect which provider
        is active so the agent can branch on it.
        """
        try:
            from ..tools import web as _web

            _web.set_runtime_config(self.config)
        except Exception as exc:
            log_debug(f"web tool runtime config sync failed: {exc}")
        is_minimax = (self.config.provider.name or "").lower() == "minimax"
        try:
            self.tool_registry.set_capabilities({"minimax_provider": is_minimax})
        except Exception as exc:
            log_debug(f"set_capabilities(minimax_provider) failed: {exc}")

    def start_agent(self, user_message: str) -> str | None:
        """Create provider + agent loop and start the background runner."""
        if not self._runtime_init_done.is_set():
            # Delay only the first agent start if background init is still running.
            self._runtime_init_done.wait(timeout=10.0)

        # Make sure host-specific advanced tools (decompiler, types,
        # scripting, web) are registered before the LLM sees the schema.
        self.ensure_advanced_tools_ready()

        try:
            provider = self._create_provider()
        except Exception as e:
            log_error(f"Provider creation failed: {e}")
            return f"Provider error: {e}"

        # Sync MiniMax web-tool runtime config + capability flags. This
        # has to happen *after* the tool registry exists (it depends on
        # tool_registry.set_capabilities) but *before* AgentLoop builds
        # the tool schema to send to the model.
        self._sync_web_tool_config()

        loop = AgentLoop(
            provider,
            self.tool_registry,
            self.config,
            self._sessions[self._active_tab_id],
            skill_registry=self._skill_registry,
            host_name=self.host_name,
        )
        self._runner = BackgroundAgentRunner(loop)
        self._runner.start(user_message)
        return None

    def get_event(self, timeout: float = 0) -> TurnEvent | None:
        if self._runner is None:
            return None
        return self._runner.get_event(timeout=timeout)

    def cancel(self) -> None:
        self._pending_messages.clear()
        if self._runner:
            self._runner.cancel()

    def queue_message(self, text: str) -> None:
        self._pending_messages.append(text)
        log_debug(f"Message queued, {len(self._pending_messages)} pending")

    def on_agent_finished(self) -> str | None:
        """Handle end-of-run cleanup and return the next queued message.

        Previously this cleared the pending queue unconditionally. That
        silently dropped any message the user typed while a run was
        active. We now keep the queue and return its head so the UI
        layer can drain one message per run completion. Cancellation
        paths (``cancel``, ``new_chat``, ``shutdown``, tab switch)
        continue to clear the queue to avoid leaking stale-context
        requests across runs.

        Returns
        -------
        str | None
            The first pending message if any remain, otherwise ``None``.
        """
        self._runner = None

        # Re-persist the instance ID in the database so a freshly created
        # IDB still gets one recorded before the next checkpoint cycle.
        set_database_instance_id(self._db_instance_id)

        session = self._sessions.get(self._active_tab_id)
        if session and self.config.checkpoint_auto_save and session.messages:
            try:
                history = SessionHistory(self.config)
                # Off-main-thread: the JSON dump of the whole transcript can
                # take long enough to visibly freeze IDA at end of turn.
                # Fire-and-forget is safe here — the next turn re-reads from
                # the in-memory session, not the file, and a missed save is
                # recovered on the next checkpoint. The single-worker
                # executor inside SessionHistory serialises back-to-back
                # saves so the latest state always wins.
                future = history.save_session_async(session)
                future.add_done_callback(self._on_async_save_done)
            except (OSError, ValueError) as e:
                log_error(f"Failed to auto-save session: {e}")

        if not self._pending_messages:
            return None
        next_message = self._pending_messages.pop(0)
        log_debug(f"Draining queue after run: {len(self._pending_messages)} remaining")
        return next_message

    @staticmethod
    def _on_async_save_done(future: Any) -> None:
        """Log the outcome of a fire-and-forget ``save_session_async`` call.

        Exceptions raised inside the worker thread are captured by the
        Future and would otherwise be silently dropped. This callback
        surfaces them so a corrupted save is visible in the log.
        """
        exc = future.exception()
        if exc is not None:
            log_error(f"Background session save failed: {exc}")

    def new_chat(self) -> None:
        """Reset the active tab to a fresh session."""
        self._pending_messages.clear()
        session = self._sessions.get(self._active_tab_id)
        if session and self.config.checkpoint_auto_save and session.messages:
            try:
                history = SessionHistory(self.config)
                # Off-main-thread for the same reason as on_agent_finished:
                # the dump freezes IDA's shared event loop otherwise. Safe to
                # fire-and-forget — the session object stays alive via the
                # Future's reference until the worker finishes.
                future = history.save_session_async(session)
                future.add_done_callback(self._on_async_save_done)
            except OSError as e:
                log_debug(f"Failed to save session on new chat: {e}")
        self._sessions[self._active_tab_id] = SessionState(
            provider_name=self.config.provider.name,
            model_name=self.config.provider.model,
            idb_path=self._idb_path,
            db_instance_id=self._db_instance_id,
        )
        log_info("Started new chat session (active tab)")

    def restore_sessions(self, latest_only: bool = False) -> list[tuple[str, SessionState]]:
        """Load saved sessions for the current idb_path and return (tab_id, session) pairs.

        When ``latest_only`` is True, only the most recent session is
        restored (legacy single-session behavior). Otherwise every
        saved session is loaded.
        """
        results: list[tuple[str, SessionState]] = []
        if not self._idb_path:
            log_debug("Skipping session restore: no database path available")
            return results
        try:
            history = SessionHistory(self.config)
            summaries = history.list_sessions(
                idb_path=self._idb_path,
                db_instance_id=self._db_instance_id,
            )
            summaries.sort(key=lambda s: s.get("created_at", 0))
            if latest_only:
                summaries = summaries[-1:]
            for summary in summaries:
                session = history.load_session(summary["id"])
                if session and session.messages:
                    tab_id = uuid.uuid4().hex[:8]
                    self._sessions[tab_id] = session
                    results.append((tab_id, session))
                    log_debug(f"Restored session {session.id} as tab {tab_id}")
        except (OSError, ValueError, KeyError) as e:
            log_error(f"Failed to restore sessions: {e}")
        if results:
            # Remove the default empty session that was created in __init__
            # and set the first restored tab as active
            if self._active_tab_id in self._sessions:
                default_session = self._sessions[self._active_tab_id]
                if not default_session.messages:
                    del self._sessions[self._active_tab_id]
            self._active_tab_id = results[-1][0]  # most recent
        return results

    def restore_session(self) -> SessionState | None:
        """Legacy: restore only the latest session into the active tab."""
        if not self._idb_path:
            log_debug("Skipping session restore: no database path available")
            return None
        try:
            history = SessionHistory(self.config)
            session = history.get_latest_session(
                idb_path=self._idb_path,
                db_instance_id=self._db_instance_id,
            )
            if session and session.messages:
                log_debug(f"Restoring session {session.id} with {len(session.messages)} messages")
                self._sessions[self._active_tab_id] = session
                log_info(f"Restored session {session.id} ({len(session.messages)} messages)")
                return session
        except (OSError, ValueError, KeyError) as e:
            log_error(f"Failed to restore session: {e}")
        return None

    def reset_for_new_file(self, new_idb_path: str) -> None:
        """Save all sessions and reset for a new database file."""
        self.cancel()
        for tab_id, session in self._sessions.items():
            if session.messages:
                try:
                    history = SessionHistory(self.config)
                    history.save_session(session)
                except (OSError, ValueError) as e:
                    log_error(f"Failed to save session {tab_id} on file change: {e}")
        self._sessions.clear()
        self._idb_path = _normalize_db_path(new_idb_path)
        self._db_instance_id = self._ensure_db_instance_id()
        tab_id = self._create_session()
        self._active_tab_id = tab_id

    def update_settings(self) -> None:
        # Re-register custom providers in case user added/removed one
        self._provider_registry.register_custom_providers(list(self.config.custom_providers.keys()))
        # Clear provider instances cache to force fresh creation with new credentials.
        # Without this, get_or_create() may return a cached instance from
        # _ModelFetcher in Settings dialog with stale internal state (e.g. cached
        # HTTP client), causing crashes when streaming starts on the next message.
        # Use the public ``retire_instances`` method instead of touching the
        # private ``_instances`` dict directly so the registry's safety
        # invariants (retire-before-clear) are preserved.
        self._provider_registry.retire_instances()
        for session in self._sessions.values():
            session.provider_name = self.config.provider.name
            session.model_name = self.config.provider.model
        # Re-arm advanced tool registration: the operator may have
        # installed Hex-Rays (or another decompiler), closed/reopened
        # the database, or otherwise changed the deferred-registration
        # retry state.  Resetting the flag makes the next prompt retry
        # the host-provided ``ensure_tools_ready`` path.
        self.reset_deferred_tools()
        # Reload skills ONLY when the skill-relevant config changed.
        # ``_reload_skills`` does a filesystem rescan (``SkillRegistry.discover``)
        # which is the dominant cost of a Settings round-trip; theme-only and
        # provider/model-only edits must not pay it. Compare the signature of
        # the two fields _reload_skills consumes before doing the work.
        new_skill_signature = self._compute_skill_config_signature()
        if new_skill_signature != self._skill_config_signature:
            self._skill_config_signature = new_skill_signature
            self._reload_skills()

    def _reload_skills(self) -> None:
        """Re-discover skills and apply current config for enabled/disabled state.

        Called after settings change so newly enabled external skills appear
        immediately without requiring an IDA restart.
        """
        if not self._runtime_init_done.is_set():
            return
        self._skill_registry.discover()
        self._skill_registry.load_external_skills(
            self.config.enabled_external_skills,
            self.config.disabled_skills,
        )

    def reload_mcp(self) -> None:
        """Reload MCP config and restart servers in the background.

        Safe to call at any time — stops existing servers first, then
        re-reads the config and starts newly-enabled servers.
        """
        thread = threading.Thread(
            target=self._mcp_manager.reload,
            args=(self.tool_registry,),
            daemon=True,
            name="rikugan-mcp-reload",
        )
        thread.start()

    def shutdown(self) -> None:
        self._runtime_shutdown.set()
        if self._runtime_init_thread.is_alive():
            self._runtime_init_done.wait(timeout=1.0)
        if self._runner:
            self._runner.cancel()
            self._runner = None
        # Final attempt to persist instance ID before the host saves the DB.
        set_database_instance_id(self._db_instance_id)
        for tab_id, session in self._sessions.items():
            if self.config.checkpoint_auto_save and session.messages:
                try:
                    history = SessionHistory(self.config)
                    history.save_session(session)
                except (OSError, ValueError) as e:
                    log_error(f"Failed to save session {tab_id} on shutdown: {e}")
        self._mcp_manager.shutdown()
