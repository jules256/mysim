"""Abstract plugin interface contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mysim.hooks import HookType
    from mysim.state import SimulationState


class Plugin(ABC):
    """Base class all simulation plugins must implement."""

    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this plugin."""
        ...

    @abstractmethod
    def priority(self) -> int:
        """Execution priority. Lower values execute first. Default: 0."""
        ...

    @abstractmethod
    def hooks(self) -> list[HookType]:
        """List of hook types this plugin subscribes to."""
        ...

    def depends_on(self) -> list[str]:
        """Optional dependency graph: names of plugins that must execute first."""
        return []

    @abstractmethod
    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        """Execute plugin logic for the given hook, returning modified state."""
        ...
