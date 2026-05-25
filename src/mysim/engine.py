"""Core simulation engine - orchestrates the annual lifecycle pipeline."""

from __future__ import annotations

import copy
import logging
from decimal import Decimal
from typing import Any

from mysim.config import AppConfig
from mysim.hooks import HOOK_ORDER, HookType
from mysim.plugin import Plugin
from mysim.state import ZERO, CapitalSource, SimulationState
from mysim.validation import validate_state

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Main simulation engine that drives the annual loop."""

    def __init__(self, config: AppConfig, plugins: list[Plugin] | None = None) -> None:
        self.config = config
        self.plugins: list[Plugin] = plugins or []
        self._sort_plugins()
        self._yearly_snapshots: list[dict[str, Any]] = []

    def _sort_plugins(self) -> None:
        """Sort plugins by priority, then by dependency graph."""
        # Build name -> plugin map
        plugin_map = {p.name(): p for p in self.plugins}

        # Topological sort respecting dependencies and priority
        sorted_plugins: list[Plugin] = []
        visited: set[str] = set()

        def visit(plugin: Plugin) -> None:
            if plugin.name() in visited:
                return
            visited.add(plugin.name())
            for dep_name in plugin.depends_on():
                if dep_name in plugin_map:
                    visit(plugin_map[dep_name])
            sorted_plugins.append(plugin)

        # Sort by priority first, then apply dependency resolution
        by_priority = sorted(self.plugins, key=lambda p: p.priority())
        for p in by_priority:
            visit(p)

        self.plugins = sorted_plugins

    def _build_initial_state(self) -> SimulationState:
        """Build the initial SimulationState from configuration."""
        sim = self.config.simulation
        start_year = sim.start_year or 2026
        age = start_year - sim.birth_year

        capital_sources: dict[str, CapitalSource] = {}
        for key, src_cfg in self.config.capital_sources.items():
            capital_sources[key] = CapitalSource(
                label=src_cfg.label,
                capital_total=src_cfg.capital_total,
                capital_cost_basis=src_cfg.capital_cost_basis,
                capital_growth_accumulated=src_cfg.capital_growth_accumulated,
                capital_growth_rate=src_cfg.capital_growth_rate,
                withdrawal_strategy=src_cfg.withdrawal_strategy,
            )

        withdrawal_order = sim.capital_withdrawal_order or list(
            self.config.capital_sources.keys()
        )

        return SimulationState(
            year=start_year,
            age=age,
            inflation_rate=sim.baseline_inflation_rate,
            capital_sources=capital_sources,
            capital_withdrawal_order=withdrawal_order,
            debug=sim.debug,
        )

    def _execute_hook(self, state: SimulationState, hook: HookType) -> SimulationState:
        """Execute all plugins registered for a given hook."""
        for plugin in self.plugins:
            if hook in plugin.hooks():
                logger.debug(
                    "Executing plugin '%s' for hook '%s' in year %d",
                    plugin.name(),
                    hook.name,
                    state.year,
                )
                state = plugin.execute(state, hook)
        return state

    def _run_single_year(self, state: SimulationState) -> SimulationState:
        """Execute the full annual pipeline for one year."""
        # Clear transient ledger entries for this year
        state.inflows = {}
        state.outflows = {}
        state.deductions = {}
        state.traces = []

        for hook in HOOK_ORDER:
            state = self._execute_hook(state, hook)

        # Compute summaries after all hooks
        state.compute_summaries()

        # Validate state invariants
        validate_state(state)

        return state

    def run(self) -> list[dict[str, Any]]:
        """Run the full simulation timeline and return yearly results."""
        sim = self.config.simulation
        start_year = sim.start_year or 2026
        end_year = sim.end_year or (sim.birth_year + 100)

        state = self._build_initial_state()

        results: list[dict[str, Any]] = []

        for year in range(start_year, end_year + 1):
            state.year = year
            state.age = year - sim.birth_year

            logger.info("Simulating year %d (age %d)", year, state.age)

            state = self._run_single_year(state)

            # Capture snapshot
            snapshot = self._capture_snapshot(state)
            results.append(snapshot)
            self._yearly_snapshots.append(snapshot)

            # Check insolvency
            if state.is_insolvent:
                if sim.insolvency_policy == "stop":
                    logger.error(
                        "Insolvency detected in year %d. Stopping simulation.", year
                    )
                    break
                else:
                    logger.warning("Insolvency detected in year %d. Continuing with debt.", year)

        return results

    def _capture_snapshot(self, state: SimulationState) -> dict[str, Any]:
        """Capture the current state as a flat dictionary for output."""
        snapshot: dict[str, Any] = {
            "year": state.year,
            "age": state.age,
            "total_inflows": state.total_inflows,
            "total_outflows": state.total_outflows,
            "total_deductions": state.total_deductions,
            "net_annual_result": state.net_annual_result,
            "is_insolvent": state.is_insolvent,
        }

        # Per-account capital totals
        for key, src in state.capital_sources.items():
            snapshot[f"capital_total_{key}"] = src.capital_total

        # Detailed deduction breakdown
        for key, entry in state.deductions.items():
            snapshot[f"deductions_{key}"] = entry.value

        # Include traces if debug mode
        if state.debug:
            snapshot["traces"] = copy.deepcopy(state.traces)

        return snapshot

    @property
    def snapshots(self) -> list[dict[str, Any]]:
        """Access the captured yearly snapshots."""
        return self._yearly_snapshots
