"""Cashflow reconciliation plugin - balances net annual cash flows."""

from __future__ import annotations

import logging
from decimal import Decimal

from mysim.config import AppConfig
from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import LedgerEntry, SimulationState, ZERO

logger = logging.getLogger(__name__)


class ReconcilePlugin(Plugin):
    """Reconciles cashflow shortfalls by withdrawing from capital or routing surpluses."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def name(self) -> str:
        return "reconcile_cashflow"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.RECONCILE_CASHFLOW]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        # Compute net result before reconciliation
        state.compute_summaries()
        net = state.net_annual_result

        if net >= ZERO:
            # Surplus: route into first capital source for compounding
            self._route_surplus(state, net)
        else:
            # Shortfall: withdraw from capital sources
            shortfall = abs(net)
            self._cover_shortfall(state, shortfall)

        return state

    def _route_surplus(self, state: SimulationState, surplus: Decimal) -> None:
        """Route positive cashflow surplus into capital sources."""
        if not state.capital_withdrawal_order:
            return

        # Route surplus into the last account in withdrawal order (investment target)
        target_key = state.capital_withdrawal_order[-1]
        if target_key in state.capital_sources:
            source = state.capital_sources[target_key]
            source.capital_cost_basis += surplus
            source.capital_total += surplus

    def _cover_shortfall(self, state: SimulationState, shortfall: Decimal) -> None:
        """Cover a cashflow shortfall by withdrawing from capital sources."""
        remaining = shortfall

        for account_key in state.capital_withdrawal_order:
            if remaining <= ZERO:
                break

            if account_key not in state.capital_sources:
                continue

            source = state.capital_sources[account_key]

            if source.capital_total <= ZERO and not state.allow_negative_capital:
                continue

            if state.allow_negative_capital:
                withdrawal = remaining
            else:
                withdrawal = min(remaining, source.capital_total)

            realized_gain = self._withdraw_from_source(source, withdrawal)
            remaining -= withdrawal

            # Inject realized gain into inflows for tax calculation
            gain_key = f"realized_gain_{account_key}"
            if gain_key in state.inflows:
                state.inflows[gain_key].value += realized_gain
            else:
                state.inflows[gain_key] = LedgerEntry(
                    value=realized_gain,
                    label=f"Realisierter Gewinn ({source.label})",
                )

            logger.debug(
                "Withdrew %s from '%s', remaining shortfall: %s",
                withdrawal,
                account_key,
                remaining,
            )

        if remaining > ZERO:
            if state.allow_negative_capital:
                logger.warning(
                    "Negative capital override active, but shortfall remains in year %d: %s",
                    state.year,
                    remaining,
                )
            else:
                logger.warning(
                    "Insolvency in year %d: uncovered shortfall of %s",
                    state.year,
                    remaining,
                )
                state.is_insolvent = True

    def _withdraw_from_source(self, source, withdrawal: Decimal) -> Decimal:
        """Execute withdrawal according to the source's strategy.

        Returns the amount of realized gain.
        """
        if source.withdrawal_strategy == "pro-rata":
            return self._withdraw_pro_rata(source, withdrawal)
        elif source.withdrawal_strategy == "gain-first":
            return self._withdraw_gain_first(source, withdrawal)
        else:
            # Default to FIFO approximation (aggregate mode)
            return self._withdraw_fifo(source, withdrawal)

    def _withdraw_pro_rata(self, source, withdrawal: Decimal) -> Decimal:
        """Withdraw proportionally from cost basis and growth."""
        if source.capital_total <= ZERO:
            basis_reduction = withdrawal
            growth_reduction = ZERO
        else:
            ratio = withdrawal / source.capital_total
            basis_reduction = source.capital_cost_basis * ratio
            growth_reduction = source.capital_growth_accumulated * ratio

        source.capital_cost_basis -= basis_reduction
        source.capital_growth_accumulated -= growth_reduction
        source.capital_total -= withdrawal
        return growth_reduction

    def _withdraw_gain_first(self, source, withdrawal: Decimal) -> Decimal:
        """Withdraw from growth first, then cost basis."""
        if withdrawal <= source.capital_growth_accumulated:
            realized_gain = withdrawal
            source.capital_growth_accumulated -= withdrawal
        else:
            realized_gain = source.capital_growth_accumulated
            remainder = withdrawal - source.capital_growth_accumulated
            source.capital_growth_accumulated = ZERO
            source.capital_cost_basis -= remainder

        source.capital_total -= withdrawal
        return realized_gain

    def _withdraw_fifo(self, source, withdrawal: Decimal) -> Decimal:
        """FIFO approximation in aggregate mode: withdraw from cost basis first.

        NOTE: This aggregate implementation will naturally produce a discrete
        realized-gain step when the tracked cost basis is consumed. For smoother
        taxable cashflow, use `pro-rata` withdrawal strategy instead.
        """
        if withdrawal <= source.capital_cost_basis:
            realized_gain = ZERO
            source.capital_cost_basis -= withdrawal
        else:
            realized_gain = withdrawal - source.capital_cost_basis
            source.capital_cost_basis = ZERO
            source.capital_growth_accumulated -= realized_gain

        source.capital_total -= withdrawal
        return realized_gain
