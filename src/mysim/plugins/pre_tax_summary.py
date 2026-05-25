"""Pre-tax summary plugin - compiles aggregate financial lines before deductions."""

from __future__ import annotations

from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import SimulationState


class PreTaxSummaryPlugin(Plugin):
    """Utility plugin that computes pre-tax summaries."""

    def name(self) -> str:
        return "pre_tax_summary"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.PRE_TAX_SUMMARY]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        # Recompute summaries so tax plugins have accurate totals
        state.compute_summaries()
        return state
