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

        # Initialize on first run
        if self._fixed_costs is None:
            self._fixed_costs = trackers.fixed_costs_living
        if self._pocket_money is None:
            self._pocket_money = trackers.pocket_money

        # Apply inflation adjustment
        inflation_factor = Decimal("1") + state.inflation_rate
        self._fixed_costs = self._fixed_costs * inflation_factor
        self._pocket_money = self._pocket_money * inflation_factor

        # Register outflows
        if self._fixed_costs > ZERO:
            state.outflows["fixed_costs_living"] = LedgerEntry(
                value=self._fixed_costs, label="Lebenshaltungskosten"
            )

        if self._pocket_money > ZERO:
            state.outflows["pocket_money"] = LedgerEntry(
                value=self._pocket_money, label="Taschengeld"
            )

        return state
