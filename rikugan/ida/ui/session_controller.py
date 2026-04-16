"""IDA session controller."""

from __future__ import annotations

from ...core.config import RikuganConfig
from ...core.host import get_database_path
from ...ui.session_controller_base import SessionControllerBase
from ..tools.registry import create_default_registry


class IdaSessionController(SessionControllerBase):
    """IDA-oriented controller."""

    def __init__(self, config: RikuganConfig):
        super().__init__(
            config=config,
            tool_registry_factory=create_default_registry,
            database_path_getter=get_database_path,
            host_name="IDA Pro",
        )


# Backwards-compatible alias
SessionController = IdaSessionController
