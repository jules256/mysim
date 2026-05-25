"""Growth plugin - applies compound capital growth after cashflow resolution."""

from __future__ import annotations

from decimal import Decimal

from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import SimulationState, ZERO


class GrowthPlugin(Plugin):
    """Applies compound growth to all capital sources."""

    def name(self) -> str:
        return "capital_growth"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.POST_PROCESS]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        for key, source in state.capital_sources.items():
            if source.capital_total <= ZERO:
                continue

            growth_amount = source.capital_total * source.capital_growth_rate

            source.capital_growth_accumulated += growth_amount
            source.capital_total += growth_amount

        return state
