"""Validation layer - Fail Loudly and Early."""

from __future__ import annotations

import logging
from decimal import Decimal

from mysim.state import ROUNDING_TOLERANCE, SimulationState

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a state invariant is violated."""

    pass


def validate_state(state: SimulationState) -> None:
    """Validate all invariants on the current simulation state."""
    _validate_capital_invariants(state)
    _validate_no_negative_capital(state)


def _validate_capital_invariants(state: SimulationState) -> None:
    """Ensure capital_total == cost_basis + growth for all accounts."""
    for key, source in state.capital_sources.items():
        expected = source.capital_cost_basis + source.capital_growth_accumulated
        discrepancy = abs(source.capital_total - expected)
        if discrepancy > ROUNDING_TOLERANCE:
            raise ValidationError(
                f"Capital invariant violation for '{key}' in year {state.year}: "
                f"total={source.capital_total}, expected={expected}, "
                f"discrepancy={discrepancy}"
            )
        elif discrepancy > Decimal("0"):
            # Auto-correct within tolerance
            source.capital_growth_accumulated = (
                source.capital_total - source.capital_cost_basis
            )
            logger.debug(
                "Auto-corrected rounding discrepancy for '%s' in year %d",
                key,
                state.year,
            )


def _validate_no_negative_capital(state: SimulationState) -> None:
    """Check for negative capital unless insolvency is flagged."""
    for key, source in state.capital_sources.items():
        if source.capital_total < Decimal("0") and not state.allow_negative_capital and not state.is_insolvent:
            raise ValidationError(
                f"Negative capital detected for '{key}' in year {state.year}: "
                f"total={source.capital_total}"
            )
