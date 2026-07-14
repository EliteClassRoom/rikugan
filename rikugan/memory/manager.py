"""MemoryWorkspaceManager: dark scaffolding facade for the central memory subsystem.

This manager wraps the registry, identity resolver, and locator into a single
controller-owned object. It binds identity evidence to a workspace, tracks
process-local generations, and produces frozen run contexts.

When ``config.memory_workspaces_enabled`` is False (the current default),
the manager operates in dark mode: it returns disabled/ephemeral bindings
and never touches the registry or workspace directories.
"""

from __future__ import annotations

from ..core.config import RikuganConfig
from .identity import IdentityResolution, MemoryIdentityResolver, ResolutionStatus
from .registry import MemoryRegistry
from .workspace import (
    IdentityRequest,
    MemoryLocator,
    MemoryRunContext,
    WorkspaceBinding,
    WorkspacePaths,
    validate_memory_id,
)


class PersistenceDisabled(RuntimeError):
    """Raised when a caller requests persistent paths while persistence is disabled."""


class MemoryWorkspaceManager:
    """Controller-owned facade for central memory workspace binding.

    Parameters
    ----------
    config:
        RikuganConfig — only ``memory_dir`` and ``memory_workspaces_enabled``
        are read.
    """

    def __init__(self, config: RikuganConfig) -> None:
        self._config = config
        self._locator = MemoryLocator(config.memory_dir)
        self._registry = MemoryRegistry(self._locator.registry_database())
        self._resolver = MemoryIdentityResolver(self._registry)
        self._binding: WorkspaceBinding | None = None
        self._database_generation = 0
        self._case_binding_generation = 0

        if config.memory_workspaces_enabled:
            self._registry.initialize()

    def bind(
        self,
        request: IdentityRequest,
        choice: object | None = None,
    ) -> IdentityResolution:
        """Bind identity evidence to a workspace and return the resolution.

        In dark mode (feature disabled), returns a disabled binding without
        touching the registry.
        """
        if not self._config.memory_workspaces_enabled:
            self._binding = WorkspaceBinding(
                memory_id="",
                state="disabled",
                display_name=request.display_name,
            )
            return IdentityResolution(
                status=ResolutionStatus.EPHEMERAL,
                binding=self._binding,
            )

        resolution = self._resolver.resolve(request, choice)
        if resolution.binding is not None:
            if self._binding is None or resolution.binding.memory_id != self._binding.memory_id:
                self._database_generation += 1
            self._binding = resolution.binding
        return resolution

    def run_context(self, active_case_id: str = "") -> MemoryRunContext:
        """Return a frozen run context for the current binding."""
        memory_id = self._binding.memory_id if self._binding is not None else ""
        return MemoryRunContext(
            binary_memory_id=memory_id,
            active_case_id=active_case_id,
            database_generation=self._database_generation,
            case_binding_generation=self._case_binding_generation,
        )

    def validate_run_context(self, context: MemoryRunContext) -> bool:
        """Return True if *context* matches the current binding/generations."""
        current = self.run_context(context.active_case_id)
        return current == context

    def require_persistent_paths(self) -> WorkspacePaths:
        """Return workspace paths for the current active binding.

        Raises ``PersistenceDisabled`` if the binding is not persistence-capable
        (disabled, ephemeral, or not yet bound).
        """
        if self._binding is None or self._binding.state not in {"active", "provisional"}:
            raise PersistenceDisabled("central memory persistence is unavailable")

        return self._locator.binary(validate_memory_id(self._binding.memory_id))

    @property
    def locator(self) -> MemoryLocator:
        """Expose the memory locator for store creation."""
        return self._locator
