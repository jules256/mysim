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

        # Step 1: Exhaust all positive capital across all sources in withdrawal order
        for account_key in state.capital_withdrawal_order:
            if remaining <= ZERO:
                break

            if account_key not in state.capital_sources:
                continue

            source = state.capital_sources[account_key]
            if source.capital_total <= ZERO:
                continue

            withdrawal = min(remaining, source.capital_total)

            self._withdraw_from_source(state, account_key, source, withdrawal)
            remaining -= withdrawal

            logger.debug(
                "Withdrew %s from '%s', remaining shortfall: %s",
                withdrawal,
                account_key,
                remaining,
            )

        # Step 2: If shortfall remains and allow_negative_capital is enabled, record as debt
        if remaining > ZERO:
            if state.allow_negative_capital:
                # Add debt to the first available capital source (or the first in withdrawal order)
                target_key = state.capital_withdrawal_order[0] if state.capital_withdrawal_order else None
                if target_key and target_key in state.capital_sources:
                    source = state.capital_sources[target_key]
                    source.capital_total -= remaining
                    # Debt is usually all cost basis reduction (liability)
                    source.capital_cost_basis -= remaining
                    logger.warning(
                        "Incurred debt of %s in account '%s' for year %d",
                        remaining,
                        target_key,
                        state.year,
                    )
                    remaining = ZERO

            if remaining > ZERO:
                logger.warning(
                    "Insolvency in year %d: uncovered shortfall of %s",
                    state.year,
                    remaining,
                )
                state.is_insolvent = True

    def _withdraw_from_source(self, state: SimulationState, account_key: str, source, withdrawal: Decimal) -> None:
        """Execute withdrawal according to the source's strategy."""
        realized_gain = ZERO
        if source.withdrawal_strategy == "pro-rata":
            realized_gain = self._withdraw_pro_rata(state, source, withdrawal)
        elif source.withdrawal_strategy == "gain-first":
            realized_gain = self._withdraw_gain_first(state, source, withdrawal)
        else:
            # Default to FIFO approximation (aggregate mode)
            realized_gain = self._withdraw_fifo(state, source, withdrawal)

        if realized_gain > ZERO:
            # Use the account_key (config key) for the dictionary key to ensure lookup success in tax plugin
            # Store in carried_over_inflows because reconciliation happens AFTER tax calculation.
            # This will be picked up by the InflowPlugin in the NEXT simulation year.
            key = f"realized_gain_{account_key}"
            state.carried_over_inflows[key] = LedgerEntry(
                value=realized_gain,
                label=f"Realisierter Gewinn ({source.label})",
                is_cash_flow=False  # Crucial: already exists in asset pool
            )

    def _withdraw_pro_rata(self, state: SimulationState, source, withdrawal: Decimal) -> Decimal:
        """Withdraw proportionally from cost basis and growth. Returns realized gain."""
        if source.capital_total <= ZERO:
            basis_reduction = withdrawal
            growth_reduction = ZERO
        else:
            ratio = withdrawal / source.capital_total
            basis_reduction = state.round_decimal(source.capital_cost_basis * ratio)
            growth_reduction = withdrawal - basis_reduction

        source.capital_cost_basis -= basis_reduction
        source.capital_growth_accumulated -= growth_reduction
        source.capital_total -= withdrawal
        return growth_reduction

    def _withdraw_gain_first(self, state: SimulationState, source, withdrawal: Decimal) -> Decimal:
        """Withdraw from growth first, then cost basis. Returns realized gain."""
        realized_gain = ZERO
        if withdrawal <= source.capital_growth_accumulated:
            source.capital_growth_accumulated -= withdrawal
            realized_gain = withdrawal
        else:
            realized_gain = source.capital_growth_accumulated
            remainder = withdrawal - source.capital_growth_accumulated
            source.capital_growth_accumulated = ZERO
            source.capital_cost_basis -= remainder

        source.capital_total -= withdrawal
        return realized_gain

    def _withdraw_fifo(self, state: SimulationState, source, withdrawal: Decimal) -> Decimal:
        """FIFO approximation in aggregate mode: withdraw from cost basis first. Returns realized gain."""
        realized_gain = ZERO
        if withdrawal <= source.capital_cost_basis:
            source.capital_cost_basis -= withdrawal
        else:
            realized_gain = withdrawal - source.capital_cost_basis
            source.capital_cost_basis = ZERO
            source.capital_growth_accumulated -= realized_gain

        source.capital_total -= withdrawal
        return realized_gain
