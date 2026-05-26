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
        sim_start_year = self._config.simulation.start_year or 2026

        # Calculate inflation-adjusted amount based on years since start
        # Starting with base amount in the first year
        years_elapsed = state.year - sim_start_year

        cumulative_inflation = (Decimal("1") + state.inflation_rate) ** years_elapsed

        fixed_costs = state.round_decimal(trackers.fixed_costs_living * cumulative_inflation)
        pocket_money = state.round_decimal(trackers.pocket_money * cumulative_inflation)

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
