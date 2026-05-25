"""Host-agnostic session controller orchestration."""

from __future__ import annotations

import copy
import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..agent.loop import AgentLoop, BackgroundAgentRunner
from ..agent.turn import TurnEvent
from ..core.config import RikuganConfig
from ..core.host import get_database_instance_id, set_database_instance_id
from ..core.logging import log_debug, log_error, log_info, log_warning
from ..core.startup_timing import end, reset_for_new_session, set_metadata, start
from ..providers.registry import ProviderRegistry
from ..skills.registry import SkillRegistry
from ..state.history import SessionHistory
from ..state.session import SessionState

if TYPE_CHECKING:
    from ..mcp.manager import MCPManager
    from ..tools.registry import ToolRegistry
else:
    MCPManager = Any
    ToolRegistry = Any


def _normalize_db_path(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))
    except OSError:
        return path


class SessionControllerBase:
    """Non-Qt orchestrator for Rikugan sessions.

    Parameters
    ----------
    ensure_tools_ready:
        Optional callback invoked before the first agent turn to register
        host-specific advanced tool modules.  Must be ``Callable[[ToolRegistry], None]``
        and is called once with ``self._tool_registry``.  Host controllers
        (e.g. ``IdaSessionController``) pass their ``register_advanced_tools``
        through this callback so that shared code does not import host-specific
        modules directly.
    reset_deferred_tools:
        Optional callback invoked by ``update_settings()`` to reset any
        host-specific deferred-tool registration cache (e.g. failed-module
        tracking).  Called with no arguments.  Host controllers pass their
        host-specific reset function through this callback.
    """

    def __init__(
        self,
        config: RikuganConfig,
        tool_registry_factory: Callable[[], ToolRegistry],
        database_path_getter: Callable[[], str],
        host_name: str,
        ensure_tools_ready: Callable[[Any], None] | None = None,
        reset_deferred_tools: Callable[[], None] | None = None,
    ):
        t_base = start("controller.base_init_total")
        self.config = config
        self.host_name = host_name
        self._provider_registry = ProviderRegistry()
        self._provider_registry.register_custom_providers(list(config.custom_providers.keys()))
        t_tools = start("tools.registry_create")
        self._tool_registry = tool_registry_factory()
        end("tools.registry_create", t_tools)
        self._advanced_tools_registered = False  # deferred until first agent turn
        self._ensure_tools_ready = ensure_tools_ready  # host-specific callback (no host import here)
        self._reset_deferred_tools = reset_deferred_tools  # host-provided callback for settings reload
        self._skill_registry = SkillRegistry()
        self._mcp_manager: MCPManager = None  # lazily created when MCP config is loaded
        self._idb_path = _normalize_db_path(database_path_getter())
        self._db_instance_id = self._ensure_db_instance_id()
        self._runtime_init_done = threading.Event()
        self._runtime_shutdown = threading.Event()
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
        end("controller.base_init_total", t_base)

    def _ensure_mcp_manager(self) -> MCPManager:
        """Lazily create the MCP manager on first use."""
        if self._mcp_manager is None:
            from ..mcp.manager import MCPManager as _MCPMgr

            self._mcp_manager = _MCPMgr()
        return self._mcp_manager

    def _sync_web_tool_config(self) -> None:
        """Expose the active runtime config to MiniMax-backed web tools.

        The web tool module is only imported when the tool is explicitly
        used or when the minimax provider is active.  At that point the
        tool module itself caches the config at first access.

        Does not require full advanced-tool registration success — the web
        module may have registered even when another advanced module failed.
        """
        is_minimax = self.config.provider.name == "minimax"
        if is_minimax:
            try:
                from ..tools import web

                web.set_runtime_config(self.config)
            except Exception as e:
                log_debug(f"Failed to sync web tool config: {e}")

    def _initialize_runtime(self) -> None:
        """Load heavy runtime components off the UI path."""
        started = time.perf_counter()
        try:
            if self._runtime_shutdown.is_set():
                return
            t_skills = start("runtime_init.skills")
            self._skill_registry.discover()
            end("runtime_init.skills", t_skills)

            # Apply disabled skills + load enabled external skills
            self._skill_registry.load_external_skills(
                self.config.enabled_external_skills,
                self.config.disabled_skills,
            )

            if self._runtime_shutdown.is_set():
                return
            mcp_mgr = self._ensure_mcp_manager()
            t_mcp_cfg = start("runtime_init.mcp_config")
            mcp_mgr.load_config()
            end("runtime_init.mcp_config", t_mcp_cfg)

            # Load enabled external MCP servers — only if configured
            if self.config.enabled_external_mcp:
                t_ext_mcp = start("runtime_init.external_mcp")
                from ..core.external_sources import discover_all_external_mcp

                external_mcp = discover_all_external_mcp()
                end("runtime_init.external_mcp", t_ext_mcp)
                enabled_set = set(self.config.enabled_external_mcp)
                if enabled_set:
                    for source_key, servers in external_mcp.items():
                        enabled = [s for s in servers if f"{source_key}:{s.name}" in enabled_set]
                        if enabled:
                            mcp_mgr.add_external_configs(enabled)

            if self._runtime_shutdown.is_set():
                return
            t_mcp_start = start("runtime_init.mcp_start")
            mcp_mgr.start_servers(self._tool_registry)
            end("runtime_init.mcp_start", t_mcp_start)
        except Exception as e:
            log_error(f"Background runtime initialization failed: {e}")
        finally:
            # Record metadata for the startup report
            try:
                set_metadata("provider", self.config.provider.name)
                set_metadata("model", self.config.provider.model)
                set_metadata("tool_count", len(self._tool_registry.list_names()))
                skill_count = (
                    len(self._skill_registry._skills)
                    if hasattr(self._skill_registry, "_skills")
                    else 0
                )
                set_metadata("skill_count", skill_count)
                mcp_enabled = sum(1 for c in (self._mcp_manager._configs if self._mcp_manager else []) if c.enabled)
                set_metadata("mcp_enabled", mcp_enabled)
            except Exception:
                pass
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
        return self._tool_registry

    @property
    def skill_slugs(self) -> list[str]:
        if not self._runtime_init_done.is_set():
            return []
        return self._skill_registry.list_slugs()

    @property
    def runtime_ready(self) -> bool:
        return self._runtime_init_done.is_set()

    def get_function_count(self) -> int:
        """Return the total number of functions in the binary.

        Override in host-specific controllers to provide real data.
        Default returns 0 (no functions available).
        """
        return 0

    def list_functions_raw(self, offset: int = 0, limit: int = 0) -> list[dict]:
        """Return a raw list of function metadata dicts for the bulk renamer.

        Override in host-specific controllers to provide real data.
        Default returns an empty list (no functions available).
        Supports chunked loading via *offset* and *limit*.
        """
        return []

    @property
    def is_agent_running(self) -> bool:
        return self._runner is not None and self._runner.agent_loop.is_running

    def get_runner(self) -> BackgroundAgentRunner | None:
        return self._runner

    def get_provider(self) -> Any:
        """Create and return an LLMProvider instance for the current config."""
        if not self._runtime_init_done.is_set():
            self._runtime_init_done.wait(timeout=10.0)
        try:
            return self._create_provider()
        except Exception as e:
            log_error(f"Provider creation failed: {e}")
            return None

    def _create_provider(self) -> Any:
        """Build the current-configured provider, applying OAuth consent when needed."""
        provider_name = self.config.provider.name
        # Apply persisted OAuth consent to the auth cache before creating
        # an Anthropic provider without an explicit API key.  This ensures
        # consent is respected even if the user started with a different
        # provider and later switched via settings (the panel_core OAuth
        # warm-up may not have run yet).
        if provider_name == "anthropic" and not self.config.provider.api_key:
            try:
                from ..providers.auth_cache import set_keychain_consent

                set_keychain_consent(self.config.oauth_consent_accepted)
            except Exception as e:
                log_debug(f"OAuth consent apply failed (non-critical): {e}")

        provider = self._provider_registry.get_or_create(
            provider_name,
            api_key=self.config.provider.api_key,
            api_base=self.config.provider.api_base,
            model=self.config.provider.model,
        )
        provider.ensure_ready()
        return provider

    def get_tool_registry(self) -> ToolRegistry:
        """Return the tool registry."""
        return self._tool_registry

    def begin_function_enumeration(self) -> None:
        """Start a function enumeration cursor (host-specific override)."""
        pass

    def next_function_chunk(self, limit: int) -> tuple[list[dict], bool]:
        """Return the next chunk and a ``more`` flag (host-specific override)."""
        return [], False

    def cancel_function_enumeration(self) -> None:
        """Cancel an active enumeration cursor (host-specific override)."""
        pass

    def ensure_advanced_tools_ready(self) -> bool:
        """Ensure deferred advanced tools are registered.

        Uses the host-provided callback — no host-specific imports here.
        Retries only previously-failed modules on subsequent calls.

        Returns True when no known failures remain (registered or no
        callback provided); returns False when registration was attempted
        but partially or fully failed.
        """
        if self._advanced_tools_registered:
            return True
        if self._ensure_tools_ready is None:
            self._advanced_tools_registered = True
            return True
        try:
            result = self._ensure_tools_ready(self._tool_registry)
            if not result.ok:
                log_warning(
                    f"Advanced tool registration partially failed: "
                    f"{len(result.failed_modules)} modules ({', '.join(result.failed_modules)}). "
                    f"Will retry on next prompt or settings reload."
                )
                return False
            self._advanced_tools_registered = True
            log_info(f"Advanced tool registration complete ({result.registered} tools)")
            return True
        except Exception as e:
            log_warning(f"Advanced tool registration failed: {e}")
            return False

    def start_agent(self, user_message: str) -> str | None:
        """Create provider + agent loop and start the background runner."""
        if not self._runtime_init_done.is_set():
            # Delay only the first agent start if background init is still running.
            self._runtime_init_done.wait(timeout=10.0)

        # Register advanced (deferred) tool modules before first agent turn.
        self.ensure_advanced_tools_ready()

        # Sync web tool runtime config for MiniMax even when advanced
        # registration is partial — the web module may have registered
        # successfully while another module failed.
        self._sync_web_tool_config()

        # Declare provider-dependent tool availability so the tool schema
        # sent to the LLM only lists tools that the active provider supports.
        self._sync_web_tool_config()
        is_minimax = self.config.provider.name == "minimax"
        self._tool_registry.set_capabilities({"minimax_provider": is_minimax})

        t_provider = start("first_prompt.provider_ready")
        try:
            provider = self._create_provider()
            provider.ensure_ready()
            end("first_prompt.provider_ready", t_provider)
        except Exception as e:
            end("first_prompt.provider_ready", t_provider)
            log_error(f"Provider creation failed: {e}")
            return f"Provider error: {e}"

        loop = AgentLoop(
            provider,
            self._tool_registry,
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

    def on_agent_finished(self) -> None:
        self._runner = None
        # Discard queued messages — context may have changed (error, cancel,
        # model switch).  The user can re-send if still relevant.
        self._pending_messages.clear()

        # Re-persist the instance ID in the database.
        set_database_instance_id(self._db_instance_id)

        session = self._sessions.get(self._active_tab_id)
        if session and self.config.checkpoint_auto_save and session.messages:
            try:
                history = SessionHistory(self.config)
                path = history.save_session(session)
                log_debug(f"Session auto-saved: {path}")
            except (OSError, ValueError) as e:
                log_error(f"Failed to auto-save session: {e}")

    def new_chat(self) -> None:
        """Reset the active tab to a fresh session."""
        self._pending_messages.clear()
        session = self._sessions.get(self._active_tab_id)
        if session and self.config.checkpoint_auto_save and session.messages:
            try:
                history = SessionHistory(self.config)
                history.save_session(session)
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
        """Load ALL saved sessions for the current idb_path and return (tab_id, session) pairs.

        If *latest_only* is True, only the most recently saved session is restored.
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
            if not summaries:
                return results
            summaries.sort(key=lambda s: s.get("created_at", 0))
            if latest_only:
                summaries = summaries[-1:]  # most recent only
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
        # Clear startup timing records for the new database
        reset_for_new_session()

    def update_settings(self) -> None:
        self._sync_web_tool_config()
        # Re-register custom providers in case user added/removed one
        self._provider_registry.register_custom_providers(list(self.config.custom_providers.keys()))
        # Reset advanced registration flag so the next agent turn retries
        # any previously failed advanced modules.
        self._advanced_tools_registered = False
        if self._reset_deferred_tools is not None:
            try:
                self._reset_deferred_tools()
            except Exception as e:
                log_warning(f"Failed to reset deferred tool registration state: {e}")
        for session in self._sessions.values():
            session.provider_name = self.config.provider.name
            session.model_name = self.config.provider.model

    def reload_mcp(self) -> None:
        """Reload MCP config and restart servers in the background.

        Safe to call at any time — stops existing servers first, then
        re-reads the config and starts newly-enabled servers.
        """
        mcp_mgr = self._ensure_mcp_manager()
        thread = threading.Thread(
            target=mcp_mgr.reload,
            args=(self._tool_registry,),
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
        if self._mcp_manager is not None:
            self._mcp_manager.shutdown()
