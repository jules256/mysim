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
        self._fixed_costs: Decimal | None = None
        self._pocket_money: Decimal | None = None

    def name(self) -> str:
        return "outflow_tracker"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.PROCESS_OUTFLOWS]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        trackers = self._config.generic_trackers
        start_year = self._config.simulation.start_year or 2026

        # Consistent years_elapsed logic: first year (years_elapsed=0) has no inflation
        years_elapsed = state.year - start_year
        inflation_multiplier = (Decimal("1") + state.inflation_rate) ** years_elapsed

        fixed_costs = trackers.fixed_costs_living * inflation_multiplier
        pocket_money = trackers.pocket_money * inflation_multiplier

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
