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
        # Inflation was already applied to state.inflation_rate,
        # but here we need the cumulative effect since the start of the simulation.
        # SRS says: "Inflation: Applied at the beginning of the cycle to raw inputs and recurring financial trackers."
        # This implies it's cumulative.
        years_elapsed = state.year - sim_start_year + 1 # +1 because inflation applies to first year too according to current impl but let's re-read SRS
        # SRS 1.2: 1. Inflation: Applied at the beginning of the cycle to raw inputs and recurring financial trackers.
        # If year 2026 is the first year, and inflation is 2%, then 2026 values should be base * 1.02?
        # The previous implementation was:
        # self._fixed_costs = trackers.fixed_costs_living (initially)
        # every year: self._fixed_costs = self._fixed_costs * (1 + state.inflation_rate)
        # So in year 1, it becomes base * (1 + rate).

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
