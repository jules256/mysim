"""Inflow plugin - calculates income sources and pension payments."""

from __future__ import annotations

from decimal import Decimal

from mysim.config import AppConfig, EventConfig
from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import LedgerEntry, SimulationState, ZERO


class InflowPlugin(Plugin):
    """Processes all income inflows: pensions and one-time events."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._events_by_year: dict[int, list[EventConfig]] = {}
        for event in config.events:
            if event.plugin == "inflow_tracker":
                self._events_by_year.setdefault(event.year, []).append(event)

    def name(self) -> str:
        return "inflow_tracker"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.PROCESS_INFLOWS]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        trackers = self._config.generic_trackers

        # Process pensions
        for pension in trackers.pensions:
            if state.year >= pension.start_year:
                # Calculate inflation-adjusted amount based on years since start
                # Starting from the first year of pension
                years_elapsed = state.year - pension.start_year + 1
                amount = pension.amount * (
                    (Decimal("1") + pension.yearly_increase_rate) ** years_elapsed
                )
                amount = state.round_decimal(amount)

                state.inflows[pension.name] = LedgerEntry(
                    value=amount, label=pension.label
                )

        # Process one-time inflow events
        if state.year in self._events_by_year:
            for event in self._events_by_year[state.year]:
                if event.action == "one_time_inflow":
                    amount = Decimal(str(event.parameters["amount"]))
                    key = f"event_{event.label.lower().replace(' ', '_')}"
                    state.inflows[key] = LedgerEntry(
                        value=amount, label=event.label
                    )

        return state
