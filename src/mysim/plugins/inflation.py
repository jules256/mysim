"""Inflation plugin - applies inflation adjustments at the start of each cycle."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mysim.config import AppConfig, EventConfig
from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import SimulationState


class InflationPlugin(Plugin):
    """Applies inflation to tracked amounts and processes timeline events."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._events_by_year: dict[int, list[EventConfig]] = {}
        for event in config.events:
            self._events_by_year.setdefault(event.year, []).append(event)

    def name(self) -> str:
        return "inflation"

    def priority(self) -> int:
        return -100  # Executes very early

    def hooks(self) -> list[HookType]:
        return [HookType.PRE_PROCESS]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        # Process scheduled events that modify baseline inflation
        if state.year in self._events_by_year:
            for event in self._events_by_year[state.year]:
                if event.plugin == "core_engine" and event.action == "update_baseline":
                    if "inflation_rate" in event.parameters:
                        state.inflation_rate = Decimal(
                            str(event.parameters["inflation_rate"])
                        )

        return state
