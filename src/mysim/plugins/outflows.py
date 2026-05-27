"""Outflow plugin - calculates inflation-adjusted expenses."""

from __future__ import annotations

from decimal import Decimal

from mysim.config import AppConfig
from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import LedgerEntry, SimulationState, ZERO


class OutflowPlugin(Plugin):
    """Processes all outflows: fixed costs and variable spending."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def name(self) -> str:
        return "outflow_tracker"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.PROCESS_OUTFLOWS]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        trackers = self._config.generic_trackers

        # Calculate years elapsed since simulation start
        years_elapsed = state.year - state.start_year

        # Inflation adjustment follows a consistent start-year logic
        # years_elapsed = current_year - start_year
        inflation_factor = (Decimal("1") + state.inflation_rate) ** years_elapsed

        fixed_costs = trackers.fixed_costs_living * inflation_factor
        pocket_money = trackers.pocket_money * inflation_factor

        # Register outflows
        if fixed_costs > ZERO:
            state.outflows["fixed_costs_living"] = LedgerEntry(
                value=fixed_costs, label="Lebenshaltungskosten"
            )

        if pocket_money > ZERO:
            state.outflows["pocket_money"] = LedgerEntry(
                value=pocket_money, label="Taschengeld"
            )

        return state
